import logging

from cis.publisher import ChangeDelegate
from cis.settings import get_config


logger = logging.getLogger(__name__)


class CISTask(object):
    def __init__(self, boto_session, vault_record, ldap_groups, additional_data):
        self.boto_session = boto_session
        self.vault_record = vault_record
        self.ldap_groups = ldap_groups
        self.additional_data = additional_data

    @property
    def publisher(self):
        config = get_config()
        return {
            'id': config('publisher_name', namespace='cis')
        }

    def _conform_sshfingerprints(self, ssh_fingerprints):
        conformant_ssh_fingerprints = []

        for fingerprint in ssh_fingerprints:
            # XXX TBD define rules around multiples and how primary is designated.
            conformant_ssh_fingerprints.append(
                {
                    'value': fingerprint.rstrip(),
                    'verified': True,
                    'primary': True,
                    'name': 'Mozilla LDAP Synced SSHFingerprint'
                }
            )

        return conformant_ssh_fingerprints

    def _conform_pgpfingerprints(self, pgp_fingerprints):
        conformant_pgp_fingerprints = []

        for fingerprint in pgp_fingerprints:
            # XXX TBD define rules around multiples and how primary is designated.
            conformant_pgp_fingerprints.append(
                {
                    'value': fingerprint.rstrip(),
                    'verified': True,
                    'primary': True,
                    'name': 'Mozilla LDAP Synced PGPFingerprint'
                }
            )

        return conformant_pgp_fingerprints

    def send(self):
        prefixed_groups = []

        for group in self.ldap_groups:
            prefixed_groups.append('ldap_' + group)

        self.vault_record['groups'] = prefixed_groups

        self.vault_record['SSHFingerprints'] = self._conform_sshfingerprints(
            self.additional_data.get('SSHFingerprints')
        )

        self.vault_record['PGPFingerprints'] = self._conform_pgpfingerprints(
            self.additional_data.get('PGPFingerprints')
        )

        cis_change = ChangeDelegate(self.publisher, {}, self.vault_record)
        cis_change.boto_session = self.boto_session

        result = cis_change.send()

        logger.info('Result of the change for user: {user} is {result}'.format(
                user=self.vault_record.get('primaryEmail'),
                result=result
            )
        )

        return result
