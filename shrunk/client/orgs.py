# shrunk - Rutgers University URL Shortener

import datetime

from pymongo.collection import ReturnDocument

from .. import roles


class OrgsClient:
    """Mixin for organization-related operations."""

    def create_organization(self, name):
        col = self.db.organizations
        rec_query = {'name': name}
        rec_insert = {'name': name, 'timeCreated': datetime.datetime.now(), 'members': []}
        res = col.find_one_and_update(rec_query, {'$setOnInsert': rec_insert}, upsert=True,
                                      return_document=ReturnDocument.BEFORE)
        # return false if organization already existed, otherwise true
        return res is None

    def delete_organization(self, name):
        self.db.organizations.delete_one({'name': name})

    def get_organization_info(self, name):
        col = self.db.organizations
        return col.find_one({'name': name})

    def is_organization_member(self, name, netid):
        col = self.db.organizations
        res = col.find_one({'name': name, 'members.netid': netid})
        return bool(res)

    def is_organization_admin(self, name, netid):
        col = self.db.organizations
        res = col.find_one({'name': name,
                            'members': {'$elemMatch': {'netid': netid,
                                                       'is_admin': True}}})
        return bool(res)

    def add_organization_member(self, name: str, netid: str, is_admin: bool = False) -> bool:
        """Add a member to an organization.

        :Parameters:
          - `name`: the name of the organization
          - `netid`: the NetID of the user to add
          - `is_admin`: whether the new user should be an organization-level administrator

        :Returns:
          True if the database was modified, false otherwise.
        """
        col = self.db.organizations
        match = {'name': name, 'members': {'$not': {'$elemMatch': {'netid': netid}}}}
        member = {'is_admin': bool(is_admin),
                  'netid': netid,
                  'timeCreated': datetime.datetime.now()}
        res = col.update_one(match, {'$addToSet': {'members': member}})
        return res.modified_count != 0

    def add_organization_admin(self, name, netid):
        if self.is_organization_member(name, netid):
            return self.set_org_admin(name, netid)
        return self.add_organization_member(name, netid, is_admin=True)

    def remove_organization_member(self, name, netid):
        col = self.db.organizations
        res = col.update_one({'name': name}, {'$pull': {'members': {'netid': netid}}})
        return res.modified_count == 1

    def agg_members(self, name):
        return [{'$match': {'name': name}},
                {'$unwind': '$members'},
                {'$replaceRoot': {'newRoot': '$members'}}]

    agg_admins = [{'$match': {'is_admin': True}}]

    def count_organization_members(self, name):
        return len(list(self.get_organization_members(name)))

    def get_organization_members(self, name):
        col = self.db.organizations
        return col.aggregate(self.agg_members(name))

    def count_organization_admins(self, name):
        return len(list(self.get_organization_admins(name)))

    def get_organization_admins(self, name):
        col = self.db.organizations
        return col.aggregate(self.agg_members(name) + self.agg_admins)

    def get_all_organizations(self):
        col = self.db.organizations
        return col.find({}, projection={'members': False})

    def get_member_organizations(self, netid):
        col = self.db.organizations
        return col.find({'members.netid': netid}, projection={'members': False})

    def get_admin_organizations(self, netid):
        col = self.db.organizations
        return col.find({'members': {'$elemMatch': {'netid': netid, 'is_admin': True}}},
                        projection={'members': False})

    def may_manage_organization(self, name, netid):
        if not self.get_organization_info(name):
            return False
        if roles.check('admin', netid):
            return 'site-admin'
        if self.is_organization_admin(name, netid):
            return 'admin'
        if self.is_organization_member(name, netid):
            return 'member'
        return False

    def get_organization_stats(self, name):
        pipeline = [
            {'$match': {'name': name}},
            {'$unwind': {'path': '$members'}},
            {'$replaceRoot': {'newRoot': '$members'}},
            {'$project': {'netid': 1}},
            {'$lookup': {'from': 'urls',
                         'localField': 'netid',
                         'foreignField': 'netid',
                         'as': 'links'}},
            {'$addFields': {'total_visits': {'$sum': '$links.visits'},
                            'unique_visits': {'$sum': '$links.unique_visits'}}},
            {'$project': {'links': 0}}
        ]

        return list(self.db.organizations.aggregate(pipeline))

    def get_geoip_json_organization(self, name):
        def not_null(field):
            return [{'$match': {field: {'$exists': True, '$ne': None}}}]

        def group_by(op):
            return [{'$group': {'_id': op, 'value': {'$sum': 1}}}]

        filter_us = [{'$match': {'country_code': 'US'}}]

        rename_id = [
            {'$addFields': {'code': '$_id'}},
            {'$project': {'_id': 0}}
        ]

        aggregation = [
            {'$match': {'name': name}},
            {'$unwind': '$members'},
            {'$lookup': {
                'from': 'urls',
                'localField': 'members.netid',
                'foreignField': 'netid',
                'as': 'links'
            }},
            {'$unwind': '$links'},
            {'$replaceRoot': {'newRoot': '$links'}},
            {'$lookup': {
                'from': 'visits',
                'localField': '_id',
                'foreignField': 'link_id',
                'as': 'visits'
            }},
            {'$unwind': '$visits'},
            {'$replaceRoot': {'newRoot': '$visits'}},
            {'$facet': {
                'us': filter_us + not_null('state_code') + group_by('$state_code') + rename_id,
                'world': not_null('country_code') + group_by('$country_code') + rename_id
            }}
        ]

        return next(self.db.organizations.aggregate(aggregation))

    def set_organization_admin(self, org_name, member_netid, is_admin):
        return self.db.organizations.update_one({'name': org_name},
                                                {'$set': {'members.$[elem].is_admin': is_admin}},
                                                array_filters=[{'elem.netid': member_netid}])

    def grant_organization_admin(self, org_name, member_netid):
        return self.set_organization_admin(org_name, member_netid, True)

    def remove_organization_admin(self, org_name, member_netid):
        return self.set_organization_admin(org_name, member_netid, False)
