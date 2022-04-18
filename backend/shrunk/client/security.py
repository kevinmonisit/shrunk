"""Implements the :py:class:`SecurityClient` class."""


from datetime import datetime, timezone
from enum import Enum
import json
from typing import Any, Dict
from bson.objectid import ObjectId
from flask import current_app
import pymongo
import requests

from .exceptions import InvalidStateChange, NoSuchObjectException

__all__ = ['SecurityClient']


class DetectedLinkStatus(Enum):
    PENDING = 'pending'
    APPROVED = 'approved'
    DENIED = 'denied'
    DETECTED = 'deleted'


class SecurityClient:
    """
    This class implements Shrunk security measures and its corresponding
    verification system.
    """

    def __init__(self, *, db: pymongo.database.Database, other_clients: Any):
        self.db = db
        self.other_clients = other_clients

    def create_pending_link(self, link_document: Dict[str, Any]):
        if self.url_exists_as_pending(link_document['long_url']):
            return None
        link_document['status'] = DetectedLinkStatus.PENDING.value
        link_document['netid_of_last_modifier'] = None

        result = self.db.unsafe_links.insert_one(link_document)
        return result.inserted_id

    def change_link_status(self,
                           link_id: ObjectId,
                           net_id: str,
                           new_status: DetectedLinkStatus):
        unsafe_link_document = self.get_unsafe_link_document(link_id)

        update = {
            '$set': {
                'status': new_status
            },
            '$push': {
                'security_update_history': {
                    'status_changed_from': unsafe_link_document['status'],
                    'status_changed_to': new_status,
                    'netid_of_modifier': net_id,
                    'timestamp': datetime.now(timezone.utc)
                }
            }
        }

        result = self.db.unsafe_links.update_one({'_id': link_id}, update)
        if result.matched_count == -1:
            raise NoSuchObjectException

        current_app.logger.warning(self.get_pending_links())

    def promote_link(self,
                     net_id: str,
                     link_id: ObjectId):

        d = self.get_unsafe_link_document(link_id)

        if d['status'] != DetectedLinkStatus.PENDING.value:
            raise InvalidStateChange

        args = [d['title'],
                d['long_url'],
                d['expiration_time'],
                d['netid'],
                d['creator_ip']]

        self.change_link_status(link_id, net_id, DetectedLinkStatus.APPROVED.value)
        link_id = self.other_clients.links.create(
                                                    *args,
                                                    viewers=d['viewers'],
                                                    editors=d['editors'],
                                                    bypass_security_measures=True
                                                 )

        return link_id

    def reject_link(self,
                    net_id: str,
                    link_id: ObjectId
                    ):
        # TODO: we double query here. might as well do and be done
        d = self.get_unsafe_link_document(link_id)
        if d['status'] != DetectedLinkStatus.PENDING.value:
            raise InvalidStateChange
        self.change_link_status(link_id, net_id, DetectedLinkStatus.DENIED.value)

    def consider_link(self,
                      link_id: ObjectId,
                      net_id: str):
        self.change_link_status(link_id, net_id, DetectedLinkStatus.PENDING.value)

    def get_unsafe_link_document(self, link_id: ObjectId) -> Any:
        result = self.db.unsafe_links.find_one({'_id': link_id})
        if result is None:
            raise NoSuchObjectException
        return result

    def url_exists_as_pending(self, long_url: str) -> Any:
        result = self.db.unsafe_links.find_one({'long_url': long_url})
        return result is not None

    def get_link_status(self, link_id: ObjectId) -> Any:
        link = self.get_unsafe_link_document(link_id)
        return link['status']

    def get_history(self):
        pass

    def get_rejected_links(self):
        pass

    def get_accepted_links(self):
        pass

    def get_pending_links(self):
        return list(self.db.unsafe_links.find({'status': DetectedLinkStatus.PENDING.value}))

    def get_number_of_pending_links(self):
        return len(self.get_pending_links())

    def security_risk_detected(self, long_url: str) -> bool:
        """Checks a url with a security risk API. In this case,
        the API is Google Safe Browsing API. For now, if the status
        code is not 200 when making a request, we continue with the link
        creation.

        The daily quota for the Lookup API is 10,000. If Google Safe Browsing
        API returns an error, this method will return false no matter what.
        This is to ensure that link creation continues despite Google Safe
        Browsing API failure.

        :param long_url: a long url to verify
        """
        API_KEY = current_app.config['GOOGLE_SAFE_BROWSING_API']

        postBody = {
            'client': {
                'clientId':      'Shrunk-Rutgers',
                'clientVersion': current_app.config['SHRUNK_VERSION']
            },
            'threatInfo': {
                'threatTypes':      ['MALWARE', 'SOCIAL_ENGINEERING'],
                'platformTypes':    ['WINDOWS'],
                'threatEntryTypes': ['URL'],
                'threatEntries': [
                    {'url': long_url},
                ]
            }
        }

        try:
            r = requests.post(
                'https://safebrowsing.googleapis.com/v4/threatMatches:find?key={}'.format(API_KEY),
                data=json.dumps(postBody)
                )
            r.raise_for_status()
            return len(r.json()['matches']) > 0
        except requests.exceptions.HTTPError as err:
            current_app.logger.warning('Google Safe Browsing API request failed. Status code: {}'.format(r.status_code))
            current_app.logger.warning(err)
        except KeyError as err:
            current_app.logger.warning('ERROR: The key {} did not exist in the JSON response'.format(err))
        except Exception as err:
            current_app.logger.warning('An unknown error was detected when calling Google Safe Browsing API')
            current_app.logger.warning(err)

        return False
