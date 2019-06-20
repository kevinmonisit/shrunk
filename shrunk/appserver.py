""" shrunk - Rutgers University URL Shortener

Sets up a Flask application for the main web server.
"""

import json
import werkzeug.useragents
import urllib.parse
import collections

from flask import make_response, request, redirect, session, render_template
from flask_sso import SSO
from flask_assets import Environment, Bundle

from shrunk.app_decorate import ShrunkFlask
from shrunk.client import BadShortURLException, ForbiddenDomainException, \
    AuthenticationException, NoSuchLinkException
import shrunk.roles as roles

from shrunk.forms import LinkForm
from shrunk.filters import strip_protocol, ensure_protocol
from shrunk.stringutil import formattime
from shrunk.statutil import *


# Create application
# ShrunkFlask extends flask and adds decorators and configs itself
app = ShrunkFlask(__name__)

# Flask-Assets stuff
assets = Environment(app)
assets.url = app.static_url_path

# Compile+minify custom bootstrap
shrunk_bootstrap = Bundle('scss/shrunk_bootstrap.scss', filters='scss,cssmin',
                          output='shrunk_bootstrap.css')
assets.register('shrunk_bootstrap', shrunk_bootstrap)

# Minify shrunk css
shrunk_css = Bundle('css/*.css', filters='cssmin', output='shrunk_css.css')
assets.register('shrunk_css', shrunk_css)

# Create JS bundles for each page
JS_BUNDLES = {
    'shrunk_js': [],
    'shrunk_index': ['js/index.js'],
    'shrunk_edit': ['js/edit.js'],
    'shrunk_qr': ['js/qrcode.js', 'js/shrunkqr.js'],
    'shrunk_stats': ['js/stats.js']
}

for bundle_name, bundle_files in JS_BUNDLES.items():
    output_name = '{}.js'.format(bundle_name)
    bundle = Bundle('js/shrunk.js', *bundle_files, filters='jsmin', output=output_name)
    assets.register(bundle_name, bundle)

# This attaches the *flask_sso* login handler to the SSO_LOGIN_URL,
# which essentially maps the SSO attributes to a dictionary and
# calls *our* login_handler, passing the attribute dictionary
ext = SSO(app=app)

# Allows us to use the function in our templates
app.jinja_env.globals.update(formattime=formattime)

@app.context_processor
def add_search_params():
    params = {}
    if 'query' in session:
        params['query'] = session['query']
    if 'all_users' in session:
        params['all_users'] = session['all_users']
    if 'sortby' in session:
        params['sortby'] = session['sortby']
    if 'p' in session:
        params['page'] = session['page']
    return params

@app.context_processor
def add_user_info():
    try:
        netid = session['user']['netid']
        return {'netid': netid, 'roles': roles.get(netid)}
    except:
        return {}

# Shibboleth handler
@ext.login_handler
def login(user_info):
    types = user_info.get("employeeType").split(";")
    netid = user_info.get("netid")

    def t(typ):
        return typ in types

    def log_failed(why):
        app.logger.info("failed login for {} (roles: {}, reason: {})"
                        .format(netid, user_info.get("employeeType"), why))

    # get info from shibboleth types
    fac_staff = t('FACULTY') or t('STAFF')

    # get info from ACLs
    is_admin = roles.check("admin", netid)
    is_power = roles.check("power_user", netid)
    is_blacklisted = roles.check("blacklisted", netid)
    is_whitelisted = roles.check("whitelisted", netid)
    is_config_whitelisted = netid in app.config["USER_WHITELIST"]

    # now make decisions regarding whether the user can login, and what privs they should get

    # blacklisted users can never login, except config-whitelisted users can't
    # be blacklisted (so OSS people can always login)
    if is_blacklisted and not is_config_whitelisted:
        log_failed("blacklisted")
        return redirect("/unauthorized")

    # config-whitelisted users are automatically made admins
    if is_config_whitelisted:
        roles.grant("admin", "Justice League", netid)

    # (if not blacklisted) facstaff can always login, but we need to grant a role
    # so the rest of the app knows what privs to give the user
    if fac_staff:
        roles.grant("facstaff", "shibboleth", netid)

    # now determine whether to allow login
    if not (is_config_whitelisted or fac_staff or is_whitelisted):
        log_failed("unauthorized")
        return redirect("/unauthorized")

    # If we get here, the user is allowed to login, and all necessary privs
    # have been granted.
    session["user"] = user_info
    return redirect("/")

@app.route('/logout')
def logout():
    if "user" not in session:
        return redirect('/')
    user = session.pop('user')
    if('DEV_LOGINS' in app.config and app.config['DEV_LOGINS']):
        if user['netid'] in ['DEV_USER', 'DEV_FACSTAFF', 'DEV_PWR_USER', 'DEV_ADMIN']:
            return redirect('/')
    return redirect('/shibboleth/Logout')

@app.route('/shrunk-login')
def render_login(**kwargs):
    """Renders the login template.

    Takes a WTForm in the keyword arguments.
    """
    if "user" in session:
        return redirect('/')
    enable_dev = 'DEV_LOGINS' in app.config and app.config['DEV_LOGINS']
    resp = make_response(render_template('login.html',
                                         shib_login='/login',
                                         dev=enable_dev,
                                         dev_user_login='/dev-user-login',
                                         dev_facstaff_login='/dev-facstaff-login',
                                         dev_admin_login='/dev-admin-login',
                                         dev_power_login='/dev-power-login',
                                         **kwargs))
    return resp

# add devlogins if necessary
if('DEV_LOGINS' in app.config and app.config['DEV_LOGINS']):
    @app.route('/dev-user-login')
    def dev_user_login():
        app.logger.info('user dev login valid')
        session['user'] = {'netid':'DEV_USER'}
        session["all_users"] = "0"
        session["sortby"] = "0"
        return redirect('/')

    @app.route('/dev-facstaff-login')
    def dev_facstaff_login():
        app.logger.info('dev facstaff login valid')
        session['user'] = {'netid': 'DEV_FACSTAFF'}
        session['all_users'] = '0'
        session['sortby'] = '0'
        if not roles.check('facstaff', 'DEV_FACSTAFF'):
            roles.grant('facstaff', 'Justice League', 'DEV_FACSTAFF')
        return redirect('/')

    @app.route('/dev-admin-login')
    def dev_admin_login():
        app.logger.info('admin dev login valid')
        session['user'] = {'netid': 'DEV_ADMIN'}
        session["all_users"] = "0"
        session["sortby"] = "0"
        if not roles.check("admin", "DEV_ADMIN"):
            roles.grant("admin", "Justice Leage", "DEV_ADMIN")
        return redirect('/')

    @app.route('/dev-power-login')
    def def_power_login():
        session['user'] = {'netid': 'DEV_PWR_USER'}
        session["all_users"] = "0"
        session["sortby"] = "0"
        if not roles.check("power_user", "DEV_PWR_USER"):
            roles.grant("power_user", "Admin McAdminface", "DEV_PWR_USER")
        return redirect("/")


@app.route('/unauthorized')
def unauthorized():
    return make_response(render_template('unauthorized.html'))


def error(message, code):
    return make_response(render_template("error.html", message=message), code)

### Views ###
# route /<short url> handle by shrunkFlaskMini

@app.route("/")
@app.require_login
def render_index(**kwargs):
    """Renders the homepage.

    Renders the homepage for the current user. By default, this renders all of
    the links owned by them. If a search has been made, then only the links
    matching their search query are shown.
    """

    netid = session['user'].get('netid')
    client = app.get_shrunk()
    # TODO init default dict and dict.update(request.args) instead of this long thing
    # Grab the current page number
    try:
        page = int(request.args["p"])
    except:
        page = 0

    def get_param(name, *, default=None, validator=None):
        if validator:
            assert default

        param = request.args.get(name)
        param = param if param is not None else session.get(name)
        param = param if param is not None else default
        if validator and not validator(param):
            param = default
        if param is not None:
            session[name] = param
        return param

    old_query = session.get('query')
    query = get_param('query')
    query_changed = query != old_query
    all_users = get_param('all_users', default='0', validator=lambda x: x in ['0', '1'])
    sortby = get_param('sortby', default='0', validator=lambda x: x in map(str, range(6)))
    def validate_page(page):
        try:
            page = int(page)
            return page >= 1
        except ValueError:
            return False
    page = int(get_param('page', default='1', validator=validate_page))
    if query_changed:
        page = 1

    # Depending on the type of user, get info from the database
    is_admin = roles.check("admin", netid)
    if is_admin:
        if query and all_users == "0":
            #search my links
            cursor = client.search(query, netid=netid)
        elif query and all_users == "1":
            #search all links
            cursor = client.search(query)
        elif all_users == "1":
            #show all links but no query
            cursor = client.get_all_urls()
        else:
            #show all of my links but no query
            cursor = client.get_urls(netid)
    else:
        if query:
            cursor = client.search(query, netid=netid)
            app.logger.info("search: {}, '{}'".format(netid, query))
        else:
            cursor = client.get_urls(netid)
            app.logger.info("render index: {}".format(netid))

    # Perform sorting, pagination and get the results
    cursor.sort(sortby)
    page, lastpage = cursor.paginate(page, app.config["MAX_DISPLAY_LINKS"])
    links = cursor.get_results()

    #choose 9 pages to display so there's not like 200 page links
    #is 9 the optimal number?

    begin_pages = -1
    end_pages = -1
    if lastpage < 10:     #9 or fewer pages
        begin_pages = 1
        end_pages = lastpage
    elif page < 5:         #display first 9 pages
        begin_pages = 1
        end_pages = 9
    elif page > lastpage - 4:     #display last 9 pages
        begin_pages = lastpage - 8
        end_pages = lastpage
    else:                       #display current page +- 4 adjacent pages
        begin_pages = page - 4
        end_pages = page + 4

    return render_template("index.html",
                           begin_pages=begin_pages,
                           end_pages=end_pages,
                           lastpage=lastpage,
                           links=links,
                           linkserver_url=app.config["LINKSERVER_URL"],
                           page=page,
                           **kwargs)


@app.route("/add", methods=["POST"])
@app.require_login
def add_link():
    """Adds a new link for the current user. and handles errors"""
    # default is no .xxx links

    client = app.get_shrunk()
    banned_regexes = app.config.get('BANNED_REGEXES', ['\.xxx'])
    form = LinkForm(request.form, banned_regexes, client)
    netid = session['user'].get('netid')

    form.long_url.data = ensure_protocol(form.long_url.data)
    if form.validate():
        kwargs = form.to_json()
        kwargs['netid'] = netid
        kwargs['title'] = kwargs['title'].strip()

        try:
            shortened = client.create_short_url(**kwargs)
            short_url = '{}/{}'.format(app.config['LINKSERVER_URL'], shortened)
            resp = {'success': {'short_url': short_url}}
            return make_plaintext_response(json.dumps(resp))
        except BadShortURLException as e:
            resp = {'errors': {'short_url': str(e)}}
            return make_plaintext_response(json.dumps(resp))
        except ForbiddenDomainException as e:
            resp = {'errors': {'long_url': str(e)}}
            return make_plaintext_response(json.dumps(resp))
    else: # WTForms detects a form validation error:
        resp = {'errors': {}}
        for name in ['title', 'long_url', 'short_url']:
            err = form.errors.get(name)
            if err:
                resp['errors'][name] = err[0]
        return make_plaintext_response(json.dumps(resp))

@app.route("/stats", methods=["GET"])
@app.require_login
def get_stats():
    # should we require owner or admin to view?

    template_data = {
        "url_info": {},
        "missing_url": False,
        "monthy_visits": []
    }

    client = app.get_shrunk()
    if 'url' in request.args:
        url = request.args['url']
        url_info = client.get_url_info(url)
    if 'url' not in request.args or not url_info:
        template_data['missing_url'] = True
    else:
        template_data['url_info'] = url_info

    return render_template("stats.html", short_url=request.args.get('url', ''), **template_data)

@app.route("/link-visits-csv", methods=["GET"])
@app.require_login
def get_link_visits_csv():
    client = app.get_shrunk()
    netid = session['user'].get('netid')
    if 'url' not in request.args:
        return error('error: request must have url', 400)
    link = request.args['url']
    if not client.is_owner_or_admin(link, netid):
        return error('error: not authorized', 401)
    csv_output = make_csv_for_links(client, [link])
    return make_plaintext_response(csv_output, filename='visits-{}.csv'.format(link))


@app.route("/search-visits-csv", methods=["GET"])
@app.require_login
def get_search_visits_csv():
    client = app.get_shrunk()
    netid = session['user'].get('netid')
    all_users = request.args.get('all_users', '0') == '1' or session.get('all_users', '0') == '1'
    if all_users and not client.is_admin(netid):
        return error('error: not authorized', 401)

    if 'search' not in request.args:
        if all_users:  # show all links for all users
            links = client.get_all_urls()
        else:  # show all links for current user
            links = client.get_urls(netid)
    else:
        search = request.args['search']
        if all_users:  # show links matching `search` for all users
            links = client.search(search)
        else:  # show links matching `search` for current user
            links = client.search(search, netid=netid)

    links = list(links)
    total_visits = sum(map(lambda l: l['visits'], links))
    max_visits = app.config.get('MAX_VISITS_FOR_CSV', 6000)  # default 6000
    if total_visits >= max_visits:
        return 'error: too many visits to create CSV', 500

    csv_output = make_csv_for_links(client, map(lambda l: l['_id'], links))
    return make_plaintext_response(csv_output, filename='visits-search.csv')

@app.route("/geoip-csv", methods=["GET"])
@app.require_login
def get_geoip_csv():
    client = app.get_shrunk()
    netid = session['user'].get('netid')

    if 'url' not in request.args:
        return error('error: request must have url', 400)
    link = request.args['url']

    if 'resolution' not in request.args:
        return error('error: request must have resolution', 400)
    resolution = request.args['resolution']
    if resolution not in ['country', 'state']:
        return ('error: invalid resolution', 400)

    if not client.is_owner_or_admin(link, netid):
        return error('error: not authorized', 401)

    if resolution == 'country':
        get_location = get_location_country
    else:  # resolution == 'state'
        get_location = get_location_state

    csv_output = make_geoip_csv(client, get_location, link)
    return make_plaintext_response(csv_output)


@app.route("/useragent-stats", methods=["GET"])
@app.require_login
def get_useragent_stats():
    client = app.get_shrunk()
    netid = session['user'].get('netid')

    if 'url' not in request.args:
        return 'error: request must have url', 400
    link = request.args['url']

    if not client.is_owner_or_admin(link, netid):
        return 'error: not authorized', 401

    stats = collections.defaultdict(lambda: collections.defaultdict(int))
    for visit in client.get_visits(link):
        user_agent = visit.get('user_agent')
        if not user_agent:
            stats['platform']['unknown'] += 1
            stats['browser']['unknown'] += 1
            continue
        ua = werkzeug.useragents.UserAgent(user_agent)
        if ua.platform:
            stats['platform'][ua.platform.title()] += 1
        if ua.browser:
            if 'Edge' in visit['user_agent']:
                stats['browser']['Msie'] += 1
            else:
                stats['browser'][ua.browser.title()] += 1

    stats_json = json.dumps(stats)
    return make_plaintext_response(stats_json)


@app.route("/referer-stats", methods=["GET"])
@app.require_login
def get_referer_stats():
    client = app.get_shrunk()
    netid = session['user'].get('netid')

    if 'url' not in request.args:
        return 'error: request must have url', 400
    link = request.args['url']

    if not client.is_owner_or_admin(link, netid):
        return 'error: not authorized', 401

    stats = collections.defaultdict(int)
    for visit in client.get_visits(link):
        domain = get_referer_domain(visit)
        if domain:
            stats[domain] += 1
        else:
            stats['unknown'] += 1

    stats_json = json.dumps(stats)
    return make_plaintext_response(stats_json)


@app.route("/monthly-visits", methods=["GET"])
@app.require_login
def monthly_visits():
    client = app.get_shrunk()
    netid = session["user"].get("netid")

    if "url" not in request.args:
        return '{"error":"request must have url"}', 400
    url = request.args['url']
    if not client.is_owner_or_admin(url, netid):
        return '{"error":"not authorized"}', 401
    visits = client.get_monthly_visits(url)
    return json.dumps(visits), 200, {"Content-Type": "application/json"}

@app.route("/daily-visits", methods=["GET"])
@app.require_login
def daily_visits():
    client = app.get_shrunk()
    netid = session["user"].get("netid")

    if "url" not in request.args:
        return '{"error":"request must have url"}', 400
    url = request.args['url']
    if not client.is_owner_or_admin(url, netid):
        return '{"error":"not authorized"}', 401
    visits = client.get_daily_visits(url)
    return json.dumps(visits), 200, {"Content-Type": "application/json"}


@app.route("/qr", methods=["GET"])
@app.require_login
def qr():
    kwargs = {
        "print": "print" in request.args,
        "url": request.args.get("url")
    }

    client = app.get_shrunk()
    if "url" in request.args and not client.get_long_url(request.args["url"]):
        kwargs["missing_url"] = True

    return render_template("qr.html", **kwargs)


@app.route("/delete", methods=["POST"])
@app.require_login
def delete_link():
    """Deletes a link."""

    client = app.get_shrunk()
    netid = session["user"].get("netid")

    app.logger.info("Deleting URL: {}".format(request.form["short_url"]))

    try:
        client.delete_url(request.form["short_url"], netid)
    except AuthenticationException:
        return error("you are not authorized to delete that link", 401)
    except NoSuchLinkException:
        return error("that link does not exists", 404)

    return redirect("/")


@app.route("/edit", methods=["POST"])
@app.require_login
def edit_link():
    """Edits a link.

    On POST, this route expects a form that contains the unique short URL that
    will be edited.
    """
    netid = session['user'].get('netid')
    client = app.get_shrunk()

    # default is no .xxx links
    banned_regexes = app.config.get('BANNED_REGEXES', ['\.xxx'])

    form = LinkForm(request.form, banned_regexes, client)
    form.long_url.data = ensure_protocol(form.long_url.data)

    # Validate form before continuing
    if form.validate():
        # Success - make the edits in the database
        kwargs = form.to_json()
        kwargs['admin'] = roles.check("admin", netid)
        kwargs['title'] = kwargs['title'].strip()
        kwargs['power_user'] = roles.check("power_user", netid)
        kwargs['old_short_url'] = request.form['old_short_url']
        try:
            client.modify_url(**kwargs)
            new_short_url = kwargs.get('short_url') or old_short_url
            resp = {'success': {
                'new_short_url': new_short_url,
                'new_title': kwargs['title'],
            }}
            return make_plaintext_response(json.dumps(resp))
        except BadShortURLException as e:
            resp = {'errors': {'short_url': str(e)}}
            return make_plaintext_response(json.dumps(resp))
        except ForbiddenDomainException as e:
            resp = {'errors': {'long_url': str(e)}}
            return make_plaintext_response(json.dumps(resp))
    else:
        resp = {'errors': {}}
        for name in ['title', 'long_url', 'short_url']:
            err = form.errors.get(name)
            if err:
                resp['errors'][name] = err[0]
        return make_plaintext_response(json.dumps(resp))

@app.route("/edit", methods=["GET"])
@app.require_login
def edit_link_form():
    netid = session['user'].get('netid')
    client = app.get_shrunk()
    # Hit the database to get information
    old_short_url = request.args["url"]
    info = client.get_url_info(old_short_url)
    if not info:
        return redirect("/")
    if not client.is_owner_or_admin(old_short_url, netid):
        return render_index(wrong_owner=True)

    info['old_short_url'] = old_short_url
    # WARNING: the dict returned by client.get_url_info includes
    # a "netid" field already, so we have to overwrite it here with
    # the correct netid.
    info['netid'] = netid
    return render_template("edit.html", **info)

@app.route("/faq")
@app.require_login
def faq():
    return render_template("faq.html")

@app.route("/admin/")
@app.require_login
@app.require_admin
def admin_panel():
    """Renders the administrator panel.

    This displays an administrator panel with navigation links to the admin
    controls.
    """
    roledata = [{"id": role, "title": roles.form_text[role]["title"]} for role in roles.valid_roles()]
    return render_template("admin.html", roledata=roledata)
