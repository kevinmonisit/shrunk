# shrunk - Rutgers University URL Shortener

"""Database-level interactions for shrunk. """
import datetime
import random
import string
import math
import enum
import pymongo
from pymongo.collection import ReturnDocument
from pymongo.collation import Collation
import geoip2.database
import shrunk.roles as roles
from shrunk.stringutil import get_domain
from shrunk.aggregations import match_short_url, monthly_visits_aggregation, daily_visits_aggregation

class BadShortURLException(Exception):
    """Raised when the there is an error with the requested short url"""

class DuplicateIdException(BadShortURLException):
    """Raised when trying to add a duplicate key to the database."""

class ForbiddenNameException(BadShortURLException):
    """Raised when trying to use a forbidden custom short URL."""

class ForbiddenDomainException(Exception):
    """Raised when trying to make a link to a forbidden domain"""

class InvalidOperationException(Exception):
    """Raised when performing an invalid operation."""

class AuthenticationException(Exception):
    """User is not authorized to do that"""

class NoSuchLinkException(Exception):
    """link was not found"""


class SortOrder(enum.IntEnum):
    TIME_DESC = 0
    """Sort by creation time, descending."""

    TIME_ASC = 1
    """Sort by creation time, ascending."""

    TITLE_ASC = 2
    """Sort by title, alphabetically."""

    TITLE_DESC = 3
    """Sort by title, reverse-alphabetically."""

    POP_ASC = 4
    """Sort by popularity (total number of visits), ascending."""

    POP_DESC = 5
    """Sort by popularity (total number of visits), descending."""


class Pagination:
    def __init__(self, page, links_per_page):
        self.page = page
        self.links_per_page = links_per_page

    def num_pages(self, total_results):
        total_results = max(1, total_results)
        return math.ceil(total_results / self.links_per_page)


class SearchResults:
    def __init__(self, results, total_results):
        self.results = results
        self.total_results = total_results

    def __len__(self):
        return len(self.results)

    def __iter__(self):
        return iter(self.results)


class ShrunkClient:
    """A class for database interactions."""

    ALPHABET = string.digits + string.ascii_lowercase
    """The alphabet used for encoding short urls."""

    URL_MIN = 46656
    """The shortest allowable URL.

    This is the value of '1000' in the URL base encoding. Guarantees that all
    URLs are at least four characters long.
    """

    URL_MAX = 2821109907455
    """The longest allowable URL.

    This is the value of 'zzzzzzzz' in the URL base encoding. Guarantees that
    all URLs do not exceed eight characters.
    """

    RESERVED_WORDS = ["add", "login", "logout", "delete", "admin", "stats", "qr",
                      "shrunk-login", "roles", "dev-user-login", "dev-admin-login",
                      "dev-power-login", "unauthorized", "link-visits-csv",
                      "search-visits-csv", "useragent-stats", "referer-stats",
                      "monthly-visits", "edit"]
    """Reserved words that cannot be used as shortened urls."""

    def __init__(self, *, DB_HOST=None, DB_PORT=27017, DB_USERNAME=None, DB_PASSWORD=None,
                 test_client=None, DB_REPLSET=None, DB_CONNECTION_STRING=None,
                 DB_NAME='shrunk', GEOLITE_PATH=None, **config):
        """Create a new client connection.

        This client uses MongoDB.

        :Parameters:
          - `DB_HOST` (optional): the hostname to connect to; defaults to "localhost"
          - `DB_PORT` (optional): the port to connect to on the server; defaults to 27017
          - `GEOLITE_PATH` (optional): path to geolite ip database
          - `DB_USERNAME` (OPTIONAL): username to login to database
          - `DB_PASSWORD` (OPTIONAL): password to login to database
          - `test_client` (optional): a mock client to use for testing
            the database default if not present
        """

        self._DB_NAME = DB_NAME
        if test_client:
            self._mongo = test_client
            self.db = self._mongo[self._DB_NAME]
        else:
            if DB_CONNECTION_STRING:
                self._DB_CONNECTION_STRING = DB_CONNECTION_STRING
            else:
                self._DB_CONNECTION_STRING = None
                self._DB_USERNAME = DB_USERNAME
                self._DB_PASSWORD = DB_PASSWORD
                self._DB_HOST = DB_HOST
                self._DB_PORT = DB_PORT
                self._DB_REPLSET = DB_REPLSET
            self.reconnect()

        self._create_indexes()
        self._set_geoip(GEOLITE_PATH)

    def _create_indexes(self):
        self.db.visits.create_index([('short_url', pymongo.ASCENDING)])
        self.db.visitors.create_index([('ip', pymongo.ASCENDING)])
        self.db.organizations.create_index([('name', pymongo.ASCENDING)], unique=True)
        self.db.organization_members.create_index([('name', pymongo.ASCENDING),
                                                   ('netid', pymongo.ASCENDING)],
                                                  unique=True)

    def reconnect(self):
        """
        mongoclient is not fork safe. this is used to create a new client
        after potentially forking
        """
        if self._DB_CONNECTION_STRING:
            self._mongo = pymongo.MongoClient(self._DB_CONNECTION_STRING,
                                              connect=False)
        else:
            self._mongo = pymongo.MongoClient(self._DB_HOST, self._DB_PORT,
                                              username=self._DB_USERNAME,
                                              password=self._DB_PASSWORD,
                                              authSource="admin", connect=False,
                                              replicaSet=self._DB_REPLSET)
        self.db = self._mongo[self._DB_NAME]

    def _set_geoip(self, GEOLITE_PATH):
        if GEOLITE_PATH:
            self._geoip = geoip2.database.Reader(GEOLITE_PATH)
        else:
            self._geoip = None

    def clone_cursor(self, cursor):
        """Clones an already existing ShrunkCursor object.

        :Parameters:
          - `cursor`: An already existing ShrunkCursor object.

        :Returns:
          Another ShrunkCursor object. A clone.
        """
        return ShrunkCursor(cursor.cursor.clone())

    def count_links(self, netid=None):
        """Counts the number of created links.

        Gives a count on the number of created links for the given NetID. If no
        specific user is specified, this returns a global count for all users.

        :Parameters:
          - `netid` (optional): Specify a NetID to count their links; if None,
            finds a global count

        :Returns:
          A nonnegative integer.
        """
        if netid:
            return self.db.urls.count_documents({"netid": netid})
        else:
            return self.db.urls.count_documents({})

    def create_short_url(self, long_url, short_url=None, netid=None, title=None):
        """Given a long URL, create a new short URL.

        Randomly creates a new short URL and updates the Shrunk database.

        :Parameters:
          - `long_url`: The original URL to shrink.
          - `short_url` (optional): A custom name for the short URL. A random
            one is generated if none is specified.
          - `netid` (optional): The creator of this URL.
          - `title` (optional): A descriptive title for this URL.

        :Returns:
          The shortened URL.

        :Raises:
          - ForbiddenNameException: if the requested name is a reserved word or
            has been banned by an administrator
          - DuplicateIdException: if the requested name is already taken
        """
        if self.is_blocked(long_url):
            raise ForbiddenDomainException("That URL is not allowed.")

        document = {
            "_id" : short_url,
            "long_url" : long_url,
            "timeCreated" : datetime.datetime.now(),
            "visits" : 0
        }
        if netid is not None:
            document["netid"] = netid
        if title is not None:
            document["title"] = title

        if short_url is not None:
            # Attempt to insert the custom URL
            if short_url in ShrunkClient.RESERVED_WORDS:
                raise ForbiddenNameException("That name is reserved.")

            try:
                response = self.db.urls.insert_one(document)
            except pymongo.errors.DuplicateKeyError:
                raise DuplicateIdException("That name already exists.")
        else:
            # Generate a unique key and update MongoDB
            response = None
            while response is None:
                try:
                    url = ShrunkClient._generate_unique_key()
                    while url in ShrunkClient.RESERVED_WORDS:
                        url = ShrunkClient._generate_unique_key()

                    document["_id"] = url
                    response = self.db.urls.insert_one(document)
                except pymongo.errors.DuplicateKeyError:
                    continue

        return str(response.inserted_id)

    def modify_url(self, old_short_url=None, admin=False, power_user=False,
                   short_url=None, **new_doc):
        """Modifies an existing URL.

        Edits the values of the url `short_url` and replaces them with the
        values specified in the keyword arguments.

        :Parameters:
          - `old_short_url`: The ID of the URL to edit.
          - `admin`: If the requester is an admin
          - `power_user`: If the requester is an power user
          - `short_url`: The new short url (for custom urls)
          - `new_doc`: All the fields to $set in the document
        """
        if self.is_blocked(new_doc["long_url"]):
            raise ForbiddenDomainException("That URL is not allowed.")

        document = self.db.urls.find_one({"_id": old_short_url})

        if not admin and not power_user:
            short_url = None

        if short_url is not None:
            if short_url in ShrunkClient.RESERVED_WORDS:
                raise ForbiddenNameException("That name is reserved.")
            else:
                document["_id"] = short_url

            if old_short_url != short_url:
                try:
                    response = self.db.urls.insert_one(document)
                except pymongo.errors.DuplicateKeyError:
                    raise DuplicateIdException("That name already exists.")
                self.db.urls.delete_one({"_id": old_short_url})
                self.db.urls.insert_one(new_doc)
            else:
                response = self.db.urls.replace_one({"_id": old_short_url}, new_doc)
        else:
            response = self.db.urls.replace_one({"_id": old_short_url}, new_doc)

        return response

    def is_admin(self, request_netid):
        """checks if netid is an admin"""
        return roles.check('admin', request_netid)

    def is_owner_or_admin(self, short_url, request_netid):
        "checks if the url is owned by the user or if the user is an admin"
        url = self.db.urls.find_one({"_id":short_url}, projection={"netid"})
        if not url:
            return roles.check("admin", request_netid)

        url_owner = url["netid"]
        requester_is_owner = url_owner == request_netid
        return requester_is_owner or self.is_admin(request_netid)

    def delete_url(self, short_url, request_netid):
        """Given a short URL, delete it from the database.

        This deletes all information associated with the short URL and wipes all
        appropriate databases.

        :Parameters:
          - `short_url`: The shortened URL to dete.
          - `request_netid`: The netid of the user requesting to delete a link

        :Returns:
          A response in JSON detailing the effect of the database operations.
        :Throws:
          AuthenticationException if the user cant edit
          NoSuchLinkException if url doesn't exist
        """
        if not self.is_owner_or_admin(short_url, request_netid):
            raise AuthenticationException()
        if self.get_url_info(short_url) is None:
            raise NoSuchLinkException()
            
        return {
            "urlDataResponse": {
                "nRemoved": self.db.urls.delete_one({
                    "_id" : short_url
                }).deleted_count
            },
            "visitDataResponse": {
                "nRemoved": self.db.visits.delete_many({
                    "short_url": short_url
                }).deleted_count
            }
        }
        
    def delete_user_urls(self, netid):
        """Deletes all URLs associated with a given NetID.

        The response, encoded as a JSON-compatible Python dict, will at least
        contained an "nRemoved" indicating the number of records removed.

        :Parameters:
          - `netid`: The NetID of the URLs to delete.

        :Returns:
          A response in JSON detailing the effect of the database operations.
        """
        if netid is None:
            return {"ok": 0, "n" : 0}
        else:
            return self.db.urls.delete_many({"netid" : netid}).raw_result

    def get_url_info(self, short_url):
        """Given a short URL, return information about it.

        This returns a dictionary containing the following fields:
          - long_url : The original unshrunk URL
          - timeCreated: The time the URL was created, expressed as an ISODate
            instance
          - netid : If it exists, the creator of the shortened URL
          - visits : The number of visits to this URL

        :Parameters:
          - `short_url`: A shortened URL
        """
        return self.db.urls.find_one({"_id" : short_url})

    def get_monthly_visits(self, short_url):
        """Given a short URL, return how many visits and new unique visiters it gets per month.

        :Parameters:
          - `short_url`: A shortened URL

        :Returns:
         An array, each of whose elements is a dict containing the data for one month.
         The fields of each dict are:
          - `_id`: a dict with keys for month and year.
          - `first_time_visits`: new visits by users who haven't seen the link yet.
          - `all_visits`: the total visits per that month.
        """
        aggregation = [match_short_url(short_url)] + monthly_visits_aggregation
        return list(self.db.visits.aggregate(aggregation))

    def get_daily_visits(self, short_url):
        """Given a short URL, return how many visits and new unique visiters it gets per month.

        :Parameters:
          - `short_url`: A shortened URL

        :Returns:
         An array, each of whose elements is a dict containing the data for one month.
         The fields of each dict are:
          - `_id`: a dict with keys for month and year.
          - `first_time_visits`: new visits by users who haven't seen the link yet.
          - `all_visits`: the total visits per that month.
        """
        aggregation = [match_short_url(short_url)] + daily_visits_aggregation
        return list(self.db.visits.aggregate(aggregation))

    def get_long_url(self, short_url):
        """Given a short URL, returns the long URL.

        Performs a case-insensitive search for the corresponding long URL.

        :Parameters:
          - `short_url`: A shortened URL

        :Returns:
          The long URL, or None if the short URL does not exist.
        """
        result = self.get_url_info(short_url)
        if result is not None:
            return result["long_url"]
        else:
            return None

    def get_visits(self, short_url):
        """Returns all visit information to the given short URL.

        :Parameters:
          - `short_url`: A shortened URL

        :Response:
          - A JSON-compatible Python dict containing the database response.
        """
        query = {'short_url': short_url}
        return SearchResults(self.db.visits.find(query), self.db.visits.count_documents(query))

    def get_num_visits(self, short_url):
        """Given a short URL, return the number of visits.

        :Parameters:
          - `short_url`: A shortened URL

        :Returns:
          A nonnegative integer indicating the number of times the URL has been
          visited, or None if the URL does not exist in the database.
        """
        document = self.db.urls.find_one({"_id" : short_url})
        return document["visits"] if document else None

    def search(self, *, query=None, netid=None, org=None, sort=None, pagination=None):
        pipeline = []

        if netid is not None:
            pipeline.append({ '$match': { 'netid': netid } })

        if org is not None:
            pipeline.append({
                '$lookup': {
                    'from': 'organization_members',
                    'localField': 'netid',
                    'foreignField': 'netid',
                    'as': 'owner_membership'
                }
            })

            pipeline.append({
                '$addFields': {
                    'owner_orgs': {
                        '$map': { 'input': '$owner_membership', 'in': '$$this.name' }
                    }
                }
            })

            pipeline.append({
                '$match': { '$expr': { '$in': [ org, '$owner_orgs' ] } }
            })

            pipeline.append({
                '$project': { 'owner_membership': False, 'owner_orgs': False }
            })

        if query is not None:
            match = {
                '$regex': query,
                '$options': 'i'
            }

            pipeline.append({
                '$match': {
                    '$or': [
                        { '_id': match },
                        { 'long_url': match },
                        { 'title': match },
                        { 'netid': match }
                    ]
                }
            })

        if sort is not None:
            try:
                sort = int(sort)
            except ValueError:
                raise IndexError('Invalid sort order.')

            if sort == SortOrder.TIME_ASC:
                sort_exp = { 'timeCreated': 1 }
            elif sort == SortOrder.TIME_DESC:
                sort_exp = { 'timeCreated': -1 }
            elif sort == SortOrder.TITLE_ASC:
                sort_exp = { 'title': 1 }
            elif sort == SortOrder.TITLE_DESC:
                sort_exp = { 'title': -1 }
            elif sort == SortOrder.POP_ASC:
                sort_exp = { 'visits': 1 }
            elif sort == SortOrder.POP_DESC:
                sort_exp = { 'visits': -1 }
            else:
                raise IndexError('Invalid sort order.')
            pipeline.append({
                '$sort': sort_exp
            })

        facet = {
            'count': [ { '$count': 'count' } ],
            'result': [ { '$skip': 0 } ]  # because this can't be empty
        }

        if pagination is not None:
            num_skip = (pagination.page - 1) * pagination.links_per_page
            facet['result'] = [
                { '$skip': num_skip },
                { '$limit': pagination.links_per_page }
            ]

        pipeline.append({
            '$facet': facet
        })

        cur = next(self.db.urls.aggregate(pipeline, collation=Collation('en')))
        count = cur['count'][0]['count']
        result = cur['result']
        return SearchResults(result, count)

    def visit(self, short_url, source_ip, user_agent, referer):
        """Visits the given URL and logs visit information.

        On visiting a URL, this is guaranteed to perform at least the following
        side effects if the URL is valid:

          - Increment the hit counter
          - Log the visitor

        If the URL is invalid, no side effects will occur.

        :Returns:
          The long URL corresponding to the short URL, or None if no such URL
          was found in the database.
        """
        self.db.urls.update_one({"_id" : short_url}, {"$inc" : {"visits" : 1}})

        self.db.visits.insert_one({
            "short_url" : short_url,
            "source_ip" : source_ip,
            "time" : datetime.datetime.now(),
            "user_agent": user_agent,
            "referer": referer
        })

    def is_blocked(self, long_url):
        """checks if a url is blocked"""
        return bool(roles.grants.find_one({
            "role": "blocked_url",
            "entity": {"$regex": "%s*" % get_domain(long_url)}
        }))

    def get_visitor_id(self, ipaddr):
        """Gets a unique, opaque identifier for an IP address.

           :Parameters:
             - `ipaddr`: a string containing an IPv4 address.

           :Returns:
             A hexadecimal string which uniquely identifies the given IP address.
        """
        rec = {'ip': str(ipaddr)}
        res = self.db.visitors.find_one_and_update(rec, {'$setOnInsert': {'ip': str(ipaddr)}},
                                                   upsert=True,
                                                   return_document=ReturnDocument.AFTER)
        return str(res['_id'])

    def get_geoip_location(self, ipaddr):
        """Gets a human-readable UTF-8 string describing the location of the given IP address.

           :Parameters:
             - `ipaddr`: a string containing an IPv4 address.

           :Returns:
             A string describing the geographic location location of the IP address,
             or the string ``"unknown"`` if the location of the IP address cannot
             be determined.
        """

        unk = 'unknown'

        if not self._geoip:
            return unk

        if ipaddr.startswith('172.31'):  # RUWireless (NB)
            return 'Rutgers New Brunswick, New Jersey, United States'
        elif ipaddr.startswith('172.27'):  # RUWireless (NWK)
            return 'Rutgers Newark, New Jersey, United States'
        # elif ipaddr.startswith('172.19'):  # CCF, but which campus?
        elif ipaddr.startswith('172.24'):  # "Camden Computing Services"
            return 'Rutgers Camden, New Jersey, United States'
        elif ipaddr.startswith('172.'):
            return 'New Jersey, United States'

        try:
            resp = self._geoip.city(ipaddr)

            # some of city,state,country may be None; those will be filtered out below
            city = resp.city.name
            state = None
            try:
                state = resp.subdivisions.most_specific.name
            except:
                pass
            country = resp.country.name

            components = [x for x in [city, state, country] if x]

            if not components:
                return unk

            return ', '.join(components)
        except:  # geoip2.errors.AddressNotFoundError:
            return unk

    def get_country_name(self, ipaddr):
        """Gets the name of the country in which the given IPv4 address is located.

           :Parameters:
             - `ipaddr`: a string containing an IPv4 address.

           :Returns:
             A string containing the full name of the country in which the address
             is located (e.g. ``"United States"``), or the string ``"unknown"``
             if the country cannot be determined.
        """

        unk = 'unknown'
        if not self._geoip:
            return unk
        if ipaddr.startswith('172.'):
            return 'United States'
        try:
            resp = self._geoip.city(ipaddr)
            return resp.country.name or unk
        except:
            return unk

    def get_state_code(self, ipaddr):
        """Gets a string describing the state or province in which the given
           IPv4 address is located.

           :Parameters:
             - `ipaddr`: a string containing an IPv4 address.

           :Returns:
             A string containing the ISO code of the state or province in which
             the address is located (e.g. ``"NY"``, ``"NJ"``, ``"VA"``) or the string
             ``"unknown"`` if the location cannot
             be determined.
        """

        unk = 'unknown'
        if not self._geoip:
            return unk
        if ipaddr.startswith('172.'):
            return 'NJ'
        try:
            resp = self._geoip.city(ipaddr)
            return resp.subdivisions.most_specific.iso_code or unk
        except:
            return unk

    def create_organization(self, name):
        col = self.db.organizations
        rec_query = {'name': name}
        rec_insert = {'name': name, 'timeCreated': datetime.datetime.now()}
        res = col.find_one_and_update(rec_query, {'$setOnInsert': rec_insert}, upsert=True,
                                      return_document=ReturnDocument.BEFORE)
        # return false if organization already existed, otherwise true
        return res is None

    def delete_organization(self, name):
        with self._mongo.start_session() as s:
            s.start_transaction()
            self.db.organization_members.remove({'name': name})
            self.db.organizations.remove({'name': name})
            s.commit_transaction()

    def get_organization_info(self, name):
        col = self.db.organizations
        return col.find_one({'name': name})

    def is_organization_member(self, name, netid):
        col = self.db.organization_members
        res = col.find_one({'name': name, 'netid': netid})
        return bool(res)

    def is_organization_admin(self, name, netid):
        col = self.db.organization_members
        res = col.find_one({'name': name, 'netid': netid})
        return res['is_admin']

    def add_organization_member(self, name, netid, is_admin=False):
        col = self.db.organization_members
        rec = {'name': name, 'netid': netid}
        rec_update = {'is_admin': is_admin}
        rec_insert = {'name': name, 'netid': netid, 'timeCreated': datetime.datetime.now()}
        res = col.find_one_and_update(rec, {'$set': rec_update, '$setOnInsert': rec_insert},
                                      upsert=True, return_document=ReturnDocument.BEFORE)
        return res is None

    def add_organization_admin(self, name, netid):
        self.add_organization_member(name, netid, is_admin=True)
        return True

    def remove_organization_member(self, name, netid):
        col = self.db.organization_members
        col.remove({'name': name, 'netid': netid})

    def remove_organization_admin(self, name, netid):
        col = self.db.organization_members
        col.update({'name': name, 'netid': netid}, {'$set': {'is_admin': False}})

    def get_organization_members(self, name):
        col = self.db.organization_members
        return col.find({'name': name})

    def get_organization_admins(self, name):
        col = self.db.organization_members
        return col.find({'name': name, 'is_admin': True})

    def get_member_organizations(self, netid):
        col = self.db.organization_members
        return col.find({'netid': netid})

    def get_admin_organizations(self, netid):
        col = self.db.organization_members
        return col.find({'netid': netid, 'is_admin': True})

    def may_manage_organization(self, netid, name):
        if not self.get_organization_info(name):
            return False
        if roles.check('admin', netid):
            return 'admin'
        if self.is_organization_admin(name, netid):
            return 'admin'
        if self.is_organization_member(name, netid):
            return 'member'
        return False

    @staticmethod
    def _generate_unique_key():
        """Generates a unique key."""
        return ShrunkClient._base_encode(random.randint(ShrunkClient.URL_MIN,
                                                        ShrunkClient.URL_MAX))

    @staticmethod
    def _base_encode(integer):
        """Encodes an integer into our arbitrary link alphabet.

        Given an integer, convert it to base-36. Letters are case-insensitive;
        this function uses uppercase arbitrarily.

        :Parameters:
          - `integer`: An integer.

        :Returns:
          A string composed of characters from ShrunkClient.ALPHABET.
          """
        length = len(ShrunkClient.ALPHABET)
        result = []
        while integer != 0:
            result.append(ShrunkClient.ALPHABET[integer % length])
            integer //= length

        return "".join(reversed(result))
