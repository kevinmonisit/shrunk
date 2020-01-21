import flask
from werkzeug.exceptions import abort

from . import roles
from .util import ldap
from .decorators import require_login


bp = flask.Blueprint('orgs', __name__, url_prefix='/orgs')


@bp.route('/', endpoint='list', methods=['GET'])
@require_login
def list_orgs(netid, client):
    """ List the organizations of which the current user is a member. """

    def org_info(org):
        return client.get_organization_info(org['name'])

    kwargs = {
        'member_orgs': list(map(org_info, client.get_member_organizations(netid))),
        'admin_orgs': list(map(org_info, client.get_admin_organizations(netid)))
    }

    return flask.render_template('organizations.html', **kwargs)


@bp.route('/toggle_admin', endpoint='toggle_admin', methods=['POST'])
@require_login
def toggle_admin(netid, client):
    name = flask.request.form.get('name')
    member_netid = flask.request.form.get('netid')
    if not name or not member_netid:
       abort(400)
    manage = client.may_manage_organization(name, netid)
    if manage not in ['admin', 'site-admin']:
       abort(403)
    client.toggle_org_admin(name, member_netid)
    if client.count_organization_admins(name) == 0:
        client.toggle_org_admin(name, member_netid)
        return flask.jsonify({'error': 'Cannot remove last administrator.'}), 400
    return flask.jsonify({'sucess': True})


@bp.route('/create', endpoint='create', methods=['POST'])
@require_login
def create_org(netid, client):
    """ Create an organization. The name of the organization to create
        should be given in the parameter 'name'. The creating user will
        automatically be made a member of the organization. """

    if not roles.check('facstaff', netid) and not roles.check('admin', netid):
        abort(403)

    name = flask.request.form.get('name')
    if not name:
        return flask.jsonify({'errors': {'name': 'You must supply a name.'}}), 400

    name = name.strip()
    if not all(c.isalnum() or c in '_-' for c in name):
        return flask.jsonify({'errors': {'name': 'Organization names must be alphanumeric.'}}), 400

    name = name.strip()
    if not client.create_organization(name):
        err = {'name': 'An organization by that name already exists.'}
        return flask.jsonify({'errors': err}), 400

    client.add_organization_admin(name, netid)
    return flask.jsonify({'success': {'name': name}})


@bp.route('/delete', endpoint='delete', methods=['POST'])
@require_login
def delete_org(netid, client):
    """ Delete an organization. The name of the organization to delete
        should be given in the parameter 'name'. """

    name = flask.request.form.get('name')
    if not name:
        abort(400)
    manage = client.may_manage_organization(name, netid)
    if manage not in ['admin', 'site-admin']:
        abort(403)
    client.delete_organization(name)
    return flask.redirect(flask.url_for('orgs.list'))


@bp.route('/manage', endpoint='manage', methods=['GET'])
@require_login
def manage_org(netid, client):
    """ Render the manage_organization page. The organization name
        should be given in the parameter 'name'. """

    name = flask.request.args.get('name')
    if not name:
        abort(400)
    manage = client.may_manage_organization(name, netid)
    if not manage:
        abort(403)
    kwargs = {
        'name': name,
        'user_is_admin': manage in ['admin', 'site-admin'],
        'user_is_member': client.is_organization_member(name, netid),
        'members': client.get_organization_members(name),
        'manage': manage
    }

    return flask.render_template('manage_organization.html', **kwargs)


@bp.route('/stats', endpoint='stats', methods=['GET'])
@require_login
def org_stats(netid, client):
    """ Render a page showing statistics for each user in the organization. """

    name = flask.request.args.get('name')
    if not name:
        abort(400)
    if not client.may_manage_organization(name, netid):
        abort(403)
    kwargs = {'name': name}
    return flask.render_template('organization_stats.html', **kwargs)


@bp.route('/stats_json', endpoint='stats_json', methods=['GET'])
@require_login
def org_stats_json(netid, client):
    name = flask.request.args.get('name')
    if not name:
        abort(400)
    if not client.may_manage_organization(name, netid):
        abort(403)
    return flask.jsonify(client.get_organization_stats(name))


@bp.route('/geoip', endpoint='stats_geoip', methods=['GET'])
@require_login
def org_geoip(netid, client):
    name = flask.request.args.get('name')
    if not name:
        abort(400)
    if not client.may_manage_organization(name, netid):
        abort(403)
    return flask.jsonify(client.get_geoip_json_organization(name))


@bp.route('/add_member', endpoint='add_member', methods=['POST'])
@require_login
def add_org_member(netid_grantor, client):
    """ Add a member to an organization. The organization name
        should be given in the parameter 'name' and the netid of the user
        to add should be given in the parameter 'netid'. """

    netid_grantee = flask.request.form.get('netid')
    if not netid_grantee:
        return flask.jsonify({'errors': {'netid': 'You must supply a NetID.'}}), 400

    name = flask.request.form.get('name')
    admin = flask.request.form.get('is_admin', 'false') == 'true'
    if not name:
        return flask.jsonify({'errors': {'name': 'You must supply a name.'}}), 400

    manage = client.may_manage_organization(name, netid_grantor)
    if not manage:
        abort(403)
    if admin and manage not in ['admin', 'site-admin']:
        abort(403)

    if not ldap.is_valid_netid(netid_grantee):
        return flask.jsonify({'errors': {'netid': 'That NetID is not valid.'}}), 400

    res = client.add_organization_member(name, netid_grantee, is_admin=admin)
    if not res:
        return flask.jsonify({'errors': {'netid': 'Member already exists.'}}), 400

    return flask.jsonify({'success': {}})


@bp.route('/remove_member', endpoint='remove_member', methods=['POST'])
@require_login
def remove_org_member(netid_remover, client):
    """ Remove a member from an organization. The organization name
        should be given in the parameter 'name' and the netid of the user
        to remove should be given in the parameter 'netid'. """

    netid_removed = flask.request.form.get('netid')
    name = flask.request.form.get('name')
    if not netid_removed or not name:
        abort(400)
    manage = client.may_manage_organization(name, netid_remover)
    if manage not in ['admin', 'site-admin'] and netid_removed != netid_remover:
        abort(403)

    if client.count_organization_admins(name) == 1:
        admins = client.get_organization_admins(name)
        # since we just checked we can assume there is only one admin
        if list(admins)[0]['netid'] == netid_removed:
            return flask.jsonify({'error': 'Cannot remove last administrator.'}), 400
    if not client.remove_organization_member(name, netid_removed):
        return flask.jsonify({'error': 'User is not an organization member.'}), 404
    return flask.jsonify({'success': {}})
