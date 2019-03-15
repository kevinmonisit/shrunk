# shrunk - Rutgers University URL Shortener

"""Flask application for the link server."""

from flask import Flask, render_template, request, redirect

import shrunk.client
from shrunk.app_decorate import ShrunkFlaskMini


# Create application
app = ShrunkFlaskMini(__name__)


### Views ###
@app.route("/<short_url>")
def redirect_link(short_url):
    """Redirects to the short URL's true destination.

    This looks up the short URL's destination in the database and performs a
    redirect, logging some information at the same time. If no such link exists,
    a not found page is shown.

    :Parameters:
      - `short_url`: A string containing a shrunk-ified URL.
    """
    client = app.get_shrunk()
    app.logger.info("{} requests {}".format(request.remote_addr, short_url))

    # Perform a lookup and redirect
    long_url = client.get_long_url(short_url)
    if long_url is None:
        return render_template("link-404.html", short_url=short_url)
    else:
        client.visit(short_url, request.remote_addr,
                     request.headers.get('User-Agent'),
                     request.headers.get('Referer'))

        # Check if a protocol exists
        if "://" in long_url:
            return redirect(long_url)
        else:
            return redirect("http://{}".format(long_url))


@app.route("/")
def render_index():
    """Renders the homepage.

    The link server will redirect to the URL for the public URL manager.
    """
    app.logger.info("Redirecting {} to shrunk".format(request.remote_addr))
    return redirect(app.config["SHRUNK_URL"])
