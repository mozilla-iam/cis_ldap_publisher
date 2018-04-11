import boto3
import json
import ldapfroms3
import logging
import os
import task
import threading

from cis.libs import utils
from cis.libs.api import Person
from cis.settings import get_config
from utils import get_secret


sl = utils.StructuredLogger(name='cis_ldap', level=logging.DEBUG)
# Logger setUp
logger = logging.getLogger('cis_ldap')


def dead_letter():
    """Send the profile to the dead letter queue for manual inspection."""
    # XXX TBD
    pass


def assume_role_session():
    # Load config
    config = get_config()
    sts = boto3.client('sts')
    sts_response = sts.assume_role(
        RoleArn=config('iam_role_arn', namespace='cis'),
        RoleSessionName=config('iam_role_session_name', namespace='cis')
    )
    logger.info('CIS Publisher role assumed.')

    return boto3.session.Session(
        aws_access_key_id=sts_response['Credentials']['AccessKeyId'],
        aws_secret_access_key=sts_response['Credentials']['SecretAccessKey'],
        aws_session_token=sts_response['Credentials']['SessionToken'],
        region_name='us-west-2'
    )

def publish(email, boto_session, cis_publisher_session, ldap_json, person_api):
    # If user valid go ahead and push them onto a list to use as a stack.
    vault_record = person_api.get_userinfo('ad|{}|{}'.format(os.getenv('LDAP_NAMESPACE'), email.split('@')[0]))
    logger.info('Preparing to process: {}'.format(email))
    logger.debug('Enriching data fields for user with: {}'.format(json.dumps(ldap_json)))

    if vault_record.get('primaryEmail') is not None:
        logger.info('A vault record has been located for user: {}'.format(email))
        t = task.CISTask(
            boto_session=cis_publisher_session,
            vault_record=vault_record,
            ldap_groups=ldap_json.get('groups'),
            additional_data=ldap_json
        )
        t.send()
    else:
        logger.warn('A user profile could not be located in the identity vault for: {}'.format(email))
        pass

def handle(event=None, context={}):
    os.environ["CIS_OAUTH2_CLIENT_ID"] = get_secret(
        'cis_ldap_publisher.client_id', dict(app='cis_ldap_publisher')
    )

    os.environ["CIS_OAUTH2_CLIENT_SECRET"] = get_secret(
        'cis_ldap_publisher.client_secret', dict(app='cis_ldap_publisher')
    )

    people = ldapfroms3.People()
    people.connect()
    people_json = people.all

    boto_session = boto3.session.Session(
        region_name='us-west-2'
    )
    cis_publisher_session = assume_role_session()

    person_api = Person(person_api_config={
            'audience': os.getenv('CIS_PERSON_API_AUDIENCE'),
            'client_id': os.getenv('CIS_OAUTH2_CLIENT_ID'),
            'client_secret': os.getenv('CIS_OAUTH2_CLIENT_SECRET'),
            'oauth2_domain': os.getenv('CIS_OAUTH2_DOMAIN'),
            'person_api_url': os.getenv('CIS_PERSON_API_URL'),
            'person_api_version': os.getenv('CIS_PERSON_API_VERSION')
        }
    )

    threads = []

    for email, data_fields in people_json.items():
        ldap_json = data_fields
        t = threading.Thread(target=publish, args=[email, boto_session, cis_publisher_session, ldap_json, person_api])
        threads.append(t)
        t.start()

    for thread in threads:
        thread.join()
