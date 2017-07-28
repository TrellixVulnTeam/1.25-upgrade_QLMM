from contextlib import contextmanager
from datetime import datetime
import json
import os
from subprocess import CalledProcessError
from textwrap import dedent

from boto.ec2.securitygroup import SecurityGroup
from boto.exception import EC2ResponseError
from mock import (
    ANY,
    call,
    create_autospec,
    MagicMock,
    Mock,
    patch,
    )

from jujuconfig import (
    get_euca_env,
    translate_to_env,
    )
from jujupy import (
    EnvJujuClient1X,
    fake_juju_client,
    JujuData,
    SimpleEnvironment,
    )
from substrate import (
    AWSAccount,
    AzureAccount,
    AzureARMAccount,
    convert_to_azure_ids,
    describe_instances,
    destroy_job_instances,
    GCEAccount,
    get_config,
    get_job_instances,
    get_libvirt_domstate,
    has_nova_instance,
    JoyentAccount,
    LXDAccount,
    make_substrate_manager,
    MAASAccount,
    MAAS1Account,
    maas_account_from_boot_config,
    OpenStackAccount,
    parse_euca,
    start_libvirt_domain,
    StillProvisioning,
    stop_libvirt_domain,
    terminate_instances,
    verify_libvirt_domain,
    contains_only_known_instances,
    attempt_terminate_instances,
    )
from tests import (
    FakeHomeTestCase,
    TestCase,
    )
import test_gce
from tests.test_winazurearm import (
    fake_init_services,
    ResourceGroup,
    ResourceGroupDetails,
    VirtualMachine,
    )
from winazurearm import ARMClient


def get_aws_env():
    return SimpleEnvironment('baz', {
        'type': 'ec2',
        'region': 'ca-west',
        'access-key': 'skeleton-key',
        'secret-key': 'secret-skeleton-key',
        })


def get_lxd_env():
    return SimpleEnvironment('mas', {
        'type': 'lxd'
        })


def get_maas_env():
    return SimpleEnvironment('mas', {
        'type': 'maas',
        'maas-server': 'http://10.0.10.10/MAAS/',
        'maas-oauth': 'a:password:string',
        'name': 'mas'
        })


def get_maas_boot_config():
    cloud_name = 'mymaas'
    boot_config = JujuData('mas', {
        'type': 'maas',
        'maas-server': 'http://10.0.10.10/MAAS/',
        'name': 'mas'
        }, juju_home='')
    boot_config.clouds = {'clouds': {cloud_name: {
        'name': cloud_name,
        'type': boot_config.provider,
        'endpoint': boot_config.get_option('maas-server'),
        }}}
    boot_config.credentials = {'credentials': {cloud_name: {'credentials': {
        'maas-oauth': 'a:password:string',
        }}}}
    return boot_config


def get_openstack_env():
    return SimpleEnvironment('foo', {
        'type': 'openstack',
        'region': 'ca-west',
        'username': 'steve',
        'password': 'skeleton',
        'tenant-name': 'marcia',
        'auth-url': 'http://example.com',
    })


def get_rax_env():
    return SimpleEnvironment('rax', {
        'type': 'rackspace',
        'region': 'DFW',
        'username': 'a-user',
        'password': 'a-pasword',
        'tenant-name': '100',
        'auth-url': 'http://rax.testing',
    })


def get_aws_environ(env):
    environ = dict(os.environ)
    environ.update(get_euca_env(env.make_config_copy()))
    return environ


def make_maas_node(hostname='juju-qa-maas-node-1.maas'):
    return {
        "status": 6,
        "macaddress_set": [
            {
                "resource_uri": "/MAAS/api/1.0/nodes/node-0123a-4567-890a",
                "mac_address": "52:54:00:71:84:bc"
            }
        ],
        "hostname": hostname,
        "zone": {
            "resource_uri": "/MAAS/api/1.0/zones/default/",
            "name": "default",
            "description": ""
        },
        "routers": [
            "e4:11:5b:0e:74:ac",
            "fe:54:00:71:84:bc"
        ],
        "netboot": True,
        "cpu_count": 1,
        "storage": 1408,
        "owner": "root",
        "system_id": "node-75e0d560-7432-11e4-bb28-525400c43ce5",
        "architecture": "amd64/generic",
        "memory": 2048,
        "power_type": "virsh",
        "tag_names": [
            "virtual"
        ],
        "ip_addresses": [
            "10.0.30.165"
        ],
        "resource_uri": "/MAAS/api/1.0/nodes/node-0123a-4567-890a"
    }


class TestTerminateInstances(TestCase):

    def test_terminate_aws(self):
        env = get_aws_env()
        with patch('subprocess.check_call') as cc_mock:
            terminate_instances(env, ['foo', 'bar'])
        environ = get_aws_environ(env)
        cc_mock.assert_called_with(
            ['euca-terminate-instances', 'foo', 'bar'], env=environ)
        self.assertEqual(
            self.log_stream.getvalue(),
            'INFO Deleting foo, bar.\n')

    def test_terminate_aws_none(self):
        env = get_aws_env()
        with patch('subprocess.check_call') as cc_mock:
            terminate_instances(env, [])
        self.assertEqual(cc_mock.call_count, 0)
        self.assertEqual(
            self.log_stream.getvalue(),
            'INFO No instances to delete.\n')

    def test_terminate_maas(self):
        env = get_maas_env()
        with patch('subprocess.check_call', autospec=True) as cc_mock:
            with patch('subprocess.check_output', autospec=True,
                       return_value='{}') as co_mock:
                terminate_instances(env, ['/A/B/C/D/node-3d/'])
        self.assertEquals(cc_mock.call_args_list, [
            call(['maas', 'login', 'mas', 'http://10.0.10.10/MAAS/api/2.0/',
                  'a:password:string']),
        ])
        co_mock.assert_called_once_with(
            ('maas', 'mas', 'machine', 'release', 'node-3d'))
        self.assertEqual(
            self.log_stream.getvalue(),
            'INFO Deleting /A/B/C/D/node-3d/.\n')

    def test_terminate_maas_none(self):
        env = get_maas_env()
        with patch('subprocess.check_call') as cc_mock:
            terminate_instances(env, [])
        self.assertEqual(cc_mock.call_count, 0)
        self.assertEqual(
            self.log_stream.getvalue(),
            'INFO No instances to delete.\n')

    def test_terminate_openstack(self):
        env = get_openstack_env()
        with patch('subprocess.check_call') as cc_mock:
            terminate_instances(env, ['foo', 'bar'])
        environ = dict(os.environ)
        environ.update(translate_to_env(env.make_config_copy()))
        cc_mock.assert_called_with(
            ['nova', 'delete', 'foo', 'bar'], env=environ)
        self.assertEqual(
            self.log_stream.getvalue(),
            'INFO Deleting foo, bar.\n')

    def test_terminate_openstack_none(self):
        env = get_openstack_env()
        with patch('subprocess.check_call') as cc_mock:
            terminate_instances(env, [])
        self.assertEqual(cc_mock.call_count, 0)
        self.assertEqual(
            self.log_stream.getvalue(),
            'INFO No instances to delete.\n')

    def test_terminate_rackspace(self):
        env = get_rax_env()
        with patch('subprocess.check_call') as cc_mock:
            terminate_instances(env, ['foo', 'bar'])
        environ = dict(os.environ)
        environ.update(translate_to_env(env.make_config_copy()))
        cc_mock.assert_called_with(
            ['nova', 'delete', 'foo', 'bar'], env=environ)
        self.assertEqual(
            self.log_stream.getvalue(),
            'INFO Deleting foo, bar.\n')

    def test_terminate_joyent(self):
        with patch('substrate.JoyentAccount.terminate_instances') as ti_mock:
            terminate_instances(
                SimpleEnvironment('foo', get_joyent_config()), ['ab', 'cd'])
        ti_mock.assert_called_once_with(['ab', 'cd'])

    def test_terminate_lxd(self):
        env = get_lxd_env()
        with patch('subprocess.check_call') as cc_mock:
            terminate_instances(env, ['foo', 'bar'])
        self.assertEqual(
            [call(['lxc', 'stop', '--force', 'foo']),
             call(['lxc', 'delete', '--force', 'foo']),
             call(['lxc', 'stop', '--force', 'bar']),
             call(['lxc', 'delete', '--force', 'bar'])],
            cc_mock.mock_calls)

    def test_terminate_unknown(self):
        env = SimpleEnvironment('foo', {'type': 'unknown'})
        with patch('subprocess.check_call') as cc_mock:
            with self.assertRaisesRegexp(
                    ValueError,
                    'This test does not support the unknown provider'):
                terminate_instances(env, ['foo'])
        self.assertEqual(cc_mock.call_count, 0)
        self.assertEqual(self.log_stream.getvalue(), '')


class TestAWSAccount(TestCase):

    def test_from_boot_config(self):
        with patch('substrate.ec2.connect_to_region', autospec=True):
            with AWSAccount.from_boot_config(SimpleEnvironment('foo', {
                    'type': 'aws',
                    'access-key': 'skeleton',
                    'region': 'france',
                    'secret-key': 'hoover',
                    })) as aws:
                self.assertEqual(aws.euca_environ, {
                    'AWS_ACCESS_KEY': 'skeleton',
                    'AWS_SECRET_KEY': 'hoover',
                    'EC2_ACCESS_KEY': 'skeleton',
                    'EC2_SECRET_KEY': 'hoover',
                    'EC2_URL': 'https://france.ec2.amazonaws.com',
                    })
                self.assertEqual(aws.region, 'france')

    def test_client_construction_failure_returns_None(self):
        with patch(
                'substrate.ec2.connect_to_region',
                autospec=True, return_value=None):
            with AWSAccount.from_boot_config(get_aws_env()) as aws:
                self.assertIsNone(aws)

    def test_iter_security_groups(self):

        def make_group():
            class FakeGroup:
                def __init__(self, name):
                    self.name, self.id = name, name + "-id"

            for name in ['foo', 'foobar', 'baz']:
                group = FakeGroup(name)
                yield group

        client = MagicMock(spec=['get_all_security_groups'])
        client.get_all_security_groups.return_value = list(make_group())
        with patch('substrate.ec2.connect_to_region',
                   return_value=client) as ctr_mock:
            with AWSAccount.from_boot_config(get_aws_env()) as aws:
                groups = list(aws.iter_security_groups())
        self.assertEqual(groups, [
            ('foo-id', 'foo'), ('foobar-id', 'foobar'), ('baz-id', 'baz')])
        self.assert_ec2_connection_call(ctr_mock)

    def assert_ec2_connection_call(self, ctr_mock):
        ctr_mock.assert_called_once_with(
            'ca-west', aws_access_key_id='skeleton-key',
            aws_secret_access_key='secret-skeleton-key')

    def test_iter_instance_security_groups(self):
        instances = [
            MagicMock(instances=[MagicMock(groups=[
                SecurityGroup(id='foo', name='bar'), ])]),
            MagicMock(instances=[MagicMock(groups=[
                SecurityGroup(id='baz', name='qux'),
                SecurityGroup(id='quxx-id', name='quxx'), ])]),
        ]
        client = MagicMock(spec=['get_all_instances'])
        client.get_all_instances.return_value = instances
        with patch('substrate.ec2.connect_to_region',
                   return_value=client) as ctr_mock:
            with AWSAccount.from_boot_config(get_aws_env()) as aws:
                groups = list(aws.iter_instance_security_groups())
        self.assertEqual(
            groups, [('foo', 'bar'), ('baz', 'qux'), ('quxx-id', 'quxx')])
        client.get_all_instances.assert_called_once_with(instance_ids=None)
        self.assert_ec2_connection_call(ctr_mock)

    def test_iter_instance_security_groups_instances(self):
        instances = [
            MagicMock(instances=[MagicMock(groups=[
                SecurityGroup(id='foo', name='bar'),
                ])]),
            MagicMock(instances=[MagicMock(groups=[
                SecurityGroup(id='baz', name='qux'),
                SecurityGroup(id='quxx-id', name='quxx'),
                ])]),
        ]
        client = MagicMock(spec=['get_all_instances'])
        client.get_all_instances.return_value = instances
        with patch('substrate.ec2.connect_to_region',
                   return_value=client) as ctr_mock:
            with AWSAccount.from_boot_config(get_aws_env()) as aws:
                    list(aws.iter_instance_security_groups(['abc', 'def']))
        client.get_all_instances.assert_called_once_with(
            instance_ids=['abc', 'def'])
        self.assert_ec2_connection_call(ctr_mock)

    def test_destroy_security_groups(self):
        client = MagicMock(spec=['delete_security_group'])
        client.delete_security_group.return_value = True
        with patch('substrate.ec2.connect_to_region',
                   return_value=client) as ctr_mock:
            with AWSAccount.from_boot_config(get_aws_env()) as aws:
                failures = aws.destroy_security_groups(
                    ['foo', 'foobar', 'baz'])
        calls = [call(name='foo'), call(name='foobar'), call(name='baz')]
        self.assertEqual(client.delete_security_group.mock_calls, calls)
        self.assertEqual(failures, [])
        self.assert_ec2_connection_call(ctr_mock)

    def test_destroy_security_failures(self):
        client = MagicMock(spec=['delete_security_group'])
        client.delete_security_group.return_value = False
        with patch('substrate.ec2.connect_to_region',
                   return_value=client) as ctr_mock:
            with AWSAccount.from_boot_config(get_aws_env()) as aws:
                failures = aws.destroy_security_groups(
                    ['foo', 'foobar', 'baz'])
        self.assertEqual(failures, ['foo', 'foobar', 'baz'])
        self.assert_ec2_connection_call(ctr_mock)

    @contextmanager
    def make_aws_connection(self, return_value):
        client = MagicMock(spec=['get_all_network_interfaces'])
        client.get_all_network_interfaces.return_value = return_value
        with patch('substrate.ec2.connect_to_region',
                   return_value=client) as ctr_mock:
            with AWSAccount.from_boot_config(get_aws_env()) as aws:
                yield aws
        self.assert_ec2_connection_call(ctr_mock)

    def make_interface(self, group_ids):
        interface = MagicMock(spec=['groups', 'delete', 'id'])
        interface.groups = [SecurityGroup(id=g) for g in group_ids]
        return interface

    def test_delete_detached_interfaces_with_id(self):
        foo_interface = self.make_interface(['bar-id'])
        baz_interface = self.make_interface(['baz-id', 'bar-id'])
        with self.make_aws_connection([foo_interface, baz_interface]) as aws:
            unclean = aws.delete_detached_interfaces(['bar-id'])
            foo_interface.delete.assert_called_once_with()
            baz_interface.delete.assert_called_once_with()
        self.assertEqual(unclean, set())

    def test_delete_detached_interfaces_without_id(self):
        baz_interface = self.make_interface(['baz-id'])
        with self.make_aws_connection([baz_interface]) as aws:
            unclean = aws.delete_detached_interfaces(['bar-id'])
        self.assertEqual(baz_interface.delete.call_count, 0)
        self.assertEqual(unclean, set())

    def prepare_delete_exception(self, error_code):
        baz_interface = self.make_interface(['bar-id'])
        e = EC2ResponseError('status', 'reason')
        e.error_code = error_code
        baz_interface.delete.side_effect = e
        return baz_interface

    def test_delete_detached_interfaces_in_use(self):
        baz_interface = self.prepare_delete_exception(
            'InvalidNetworkInterface.InUse')
        with self.make_aws_connection([baz_interface]) as aws:
            unclean = aws.delete_detached_interfaces(['bar-id', 'foo-id'])
        baz_interface.delete.assert_called_once_with()
        self.assertEqual(unclean, set(['bar-id']))

    def test_delete_detached_interfaces_not_found(self):
        baz_interface = self.prepare_delete_exception(
            'InvalidNetworkInterfaceID.NotFound')
        with self.make_aws_connection([baz_interface]) as aws:
            unclean = aws.delete_detached_interfaces(['bar-id', 'foo-id'])
        baz_interface.delete.assert_called_once_with()
        self.assertEqual(unclean, set(['bar-id']))

    def test_delete_detached_interfaces_other(self):
        baz_interface = self.prepare_delete_exception(
            'InvalidNetworkInterfaceID')
        with self.make_aws_connection([baz_interface]) as aws:
            with self.assertRaises(EC2ResponseError):
                aws.delete_detached_interfaces(['bar-id', 'foo-id'])


def get_os_config():
    return {
        'type': 'openstack', 'username': 'foo', 'password': 'bar',
        'tenant-name': 'baz', 'auth-url': 'qux', 'region': 'quxx'}


def get_os_boot_config():
    return SimpleEnvironment('foo', get_os_config())


def make_os_security_groups(names, non_juju=()):
    groups = []
    for name in names:
        group = Mock(id='{}-id'.format(name))
        group.name = name
        if name in non_juju:
            group.description = 'asdf'
        else:
            group.description = 'juju group'
        groups.append(group)
    return groups


def make_os_security_group_instance(names):
    instance_id = '-'.join(names) + '-id'
    return MagicMock(
        id=instance_id, security_groups=[{'name': n} for n in names])


class TestOpenstackAccount(TestCase):

    def test_from_boot_config(self):
        with OpenStackAccount.from_boot_config(
                get_os_boot_config()) as account:
            self.assertEqual(account._username, 'foo')
            self.assertEqual(account._password, 'bar')
            self.assertEqual(account._tenant_name, 'baz')
            self.assertEqual(account._auth_url, 'qux')
            self.assertEqual(account._region_name, 'quxx')

    def test_get_client(self):
        with OpenStackAccount.from_boot_config(
                get_os_boot_config()) as account:
            with patch('novaclient.client.Client') as ncc_mock:
                account.get_client()
        ncc_mock.assert_called_once_with(
            '1.1', 'foo', 'bar', 'baz', 'qux', region_name='quxx',
            service_type='compute', insecure=False)

    def test_iter_security_groups(self):
        with OpenStackAccount.from_boot_config(
                get_os_boot_config()) as account:
            with patch.object(account, 'get_client') as gc_mock:
                client = gc_mock.return_value
                groups = make_os_security_groups(['foo', 'bar', 'baz'])
                client.security_groups.list.return_value = groups
                result = account.iter_security_groups()
            self.assertEqual(list(result), [
                ('foo-id', 'foo'), ('bar-id', 'bar'), ('baz-id', 'baz')])

    def test_iter_security_groups_non_juju(self):
        with OpenStackAccount.from_boot_config(
                get_os_boot_config()) as account:
            with patch.object(account, 'get_client') as gc_mock:
                client = gc_mock.return_value
                groups = make_os_security_groups(
                    ['foo', 'bar', 'baz'], non_juju=['foo', 'baz'])
                client.security_groups.list.return_value = groups
                result = account.iter_security_groups()
            self.assertEqual(list(result), [('bar-id', 'bar')])

    def test_iter_instance_security_groups(self):
        with OpenStackAccount.from_boot_config(
                get_os_boot_config()) as account:
            with patch.object(account, 'get_client') as gc_mock:
                client = gc_mock.return_value
                instance = MagicMock(security_groups=[{'name': 'foo'}])
                client.servers.list.return_value = [instance]
                groups = make_os_security_groups(['foo', 'bar'])
                client.security_groups.list.return_value = groups
                result = account.iter_instance_security_groups()
            self.assertEqual(list(result), [('foo-id', 'foo')])

    def test_iter_instance_security_groups_instance_ids(self):
        with OpenStackAccount.from_boot_config(
                get_os_boot_config()) as account:
            with patch.object(account, 'get_client') as gc_mock:
                client = gc_mock.return_value
                foo_bar = make_os_security_group_instance(['foo', 'bar'])
                baz_bar = make_os_security_group_instance(['baz', 'bar'])
                client.servers.list.return_value = [foo_bar, baz_bar]
                groups = make_os_security_groups(['foo', 'bar', 'baz'])
                client.security_groups.list.return_value = groups
                result = account.iter_instance_security_groups(['foo-bar-id'])
        self.assertEqual(list(result), [('foo-id', 'foo'), ('bar-id', 'bar')])


def get_joyent_config():
    return {
        'type': 'joyent',
        'sdc-url': 'http://example.org/sdc',
        'manta-user': 'user@manta.org',
        'manta-key-id': 'key-id@manta.org',
        'manta-url': 'http://us-east.manta.example.org',
        'private-key': 'key\abc\n'
        }


class TestJoyentAccount(TestCase):

    def test_from_boot_config(self):
        boot_config = SimpleEnvironment('foo', get_joyent_config())
        with JoyentAccount.from_boot_config(boot_config) as account:
            self.assertEqual(
                open(account.client.key_path).read(), 'key\abc\n')
        self.assertFalse(os.path.exists(account.client.key_path))
        self.assertTrue(account.client.key_path.endswith('joyent.key'))
        self.assertEqual(account.client.sdc_url, 'http://example.org/sdc')
        self.assertEqual(account.client.account, 'user@manta.org')
        self.assertEqual(account.client.key_id, 'key-id@manta.org')

    def test_terminate_instances(self):
        client = Mock()
        account = JoyentAccount(client)
        client._list_machines.return_value = {'state': 'stopped'}
        account.terminate_instances(['asdf'])
        client.stop_machine.assert_called_once_with('asdf')
        self.assertEqual(client._list_machines.mock_calls,
                         [call('asdf'), call('asdf')])
        client.delete_machine.assert_called_once_with('asdf')

    def test_terminate_instances_waits_for_stopped(self):
        client = Mock()
        account = JoyentAccount(client)
        machines = iter([{'state': 'foo'}, {'state': 'bar'},
                         {'state': 'stopped'}])
        client._list_machines.side_effect = lambda x: machines.next()
        with patch('substrate.sleep'):
            account.terminate_instances(['asdf'])
        client.stop_machine.assert_called_once_with('asdf')
        self.assertEqual(client._list_machines.call_count, 3)
        client.delete_machine.assert_called_once_with('asdf')

    def test_terminate_instances_stop_failure(self):
        client = Mock()
        account = JoyentAccount(client)
        client._list_machines.return_value = {'state': 'foo'}
        with patch('substrate.sleep'):
            with patch('substrate.until_timeout', return_value=[]):
                with self.assertRaisesRegexp(
                        Exception, 'Instance did not stop: asdf'):
                    account.terminate_instances(['asdf'])

    def test_terminate_instances_still_provisioning(self):
        client = Mock()
        account = JoyentAccount(client)
        machines = {
            'a': {'state': 'stopped'},
            'b': {'state': 'provisioning'},
            'c': {'state': 'provisioning'},
            }
        client._list_machines.side_effect = machines.get
        with self.assertRaises(StillProvisioning) as exc:
            account.terminate_instances(['b', 'c', 'a'])
        self.assertEqual(exc.exception.instance_ids, ['b', 'c'])
        client.delete_machine.assert_called_once_with('a')


def get_lxd_config():
    return {'type': 'lxd'}


class TestLXDAccount(TestCase):
    def test_from_boot_config(self):
        boot_config = SimpleEnvironment('foo', get_lxd_config())
        with LXDAccount.from_boot_config(boot_config) as account:
            self.assertIsNone(account.remote)
        boot_config.set_region('lxd-server')
        with LXDAccount.from_boot_config(boot_config) as account:
            self.assertEqual('lxd-server', account.remote)

    def test_terminate_instances(self):
        account = LXDAccount()
        with patch('subprocess.check_call', autospec=True) as cc_mock:
            account.terminate_instances(['asdf'])
        self.assertEqual(
            [call(['lxc', 'stop', '--force', 'asdf']),
             call(['lxc', 'delete', '--force', 'asdf'])],
            cc_mock.mock_calls)

    def test_terminate_instances_with_remote(self):
        account = LXDAccount(remote='lxd-server')
        with patch('subprocess.check_call', autospec=True) as cc_mock:
            account.terminate_instances(['asdf'])
        self.assertEqual(
            [call(['lxc', 'stop', '--force', 'asdf']),
             call(['lxc', 'delete', '--force', 'lxd-server:asdf'])],
            cc_mock.mock_calls)


def get_gce_config():
    return {
        'type': 'gce',
        'client-email': 'me@serviceaccount.google.com',
        'private-key': 'KEY',
        'project-id': 'test-project',
    }


class TestGCEAccount(FakeHomeTestCase):

    def test_from_boot_config(self):
        boot_config = JujuData('foo', get_gce_config())
        boot_config.credentials['credentials'] = {'google': {'baz': {}}}
        client = test_gce.make_fake_client()
        with patch('gce.get_client', return_value=client) as gc_mock:
            with GCEAccount.from_boot_config(boot_config) as account:
                self.assertIs(client, account.client)
                args = gc_mock.call_args[0]
                self.assertEqual('me@serviceaccount.google.com', args[0])
                self.assertEqual('test-project', args[2])
                with open(args[1], 'r') as kf:
                    key = kf.read()
                self.assertEqual('KEY', key)

    def test_terminate_instances(self):
        client = test_gce.make_fake_client()
        account = GCEAccount(client)
        with patch('gce.delete_instances',
                   autospec=True, return_value=1) as di_mock:
            account.terminate_instances(['juju-1', 'juju-2'])
        self.assertEqual(
            [call(client, 'juju-1', old_age=0),
             call(client, 'juju-2', old_age=0)],
            di_mock.mock_calls)

    def test_terminate_instances_exception(self):
        client = test_gce.make_fake_client()
        account = GCEAccount(client)
        with patch('gce.delete_instances',
                   autospec=True, return_value=0) as di_mock:
            with self.assertRaises(Exception):
                account.terminate_instances(['juju-1', 'juju-2'])
        di_mock.assert_called_once_with(client, 'juju-1', old_age=0)


def make_sms(instance_ids):
    from azure import servicemanagement as sm
    client = create_autospec(sm.ServiceManagementService('foo', 'bar'))

    services = AzureAccount.convert_instance_ids(instance_ids)

    def get_hosted_service_properties(service, embed_detail):
        props = sm.HostedService()
        deployment = sm.Deployment()
        deployment.name = service + '-v3'
        for role_name in services[service]:
            role = sm.Role()
            role.role_name = role_name
            deployment.role_list.roles.append(role)
        props.deployments.deployments.append(deployment)
        return props

    client.get_hosted_service_properties.side_effect = (
        get_hosted_service_properties)
    client.get_operation_status.return_value = Mock(status='Succeeded')
    client.delete_role.return_value = sm.AsynchronousOperationResult()
    return client


class TestAzureAccount(TestCase):

    def test_from_boot_config(self):
        config = {'type': 'azure',
                  'management-subscription-id': 'fooasdfbar',
                  'management-certificate': 'ab\ncd\n'}
        boot_config = SimpleEnvironment('foo', config)
        with AzureAccount.from_boot_config(boot_config) as substrate:
            self.assertEqual(substrate.service_client.subscription_id,
                             'fooasdfbar')
            self.assertEqual(open(substrate.service_client.cert_file).read(),
                             'ab\ncd\n')
        self.assertFalse(os.path.exists(substrate.service_client.cert_file))

    def test_convert_instance_ids(self):
        converted = AzureAccount.convert_instance_ids([
            'foo-bar-baz', 'foo-bar-qux', 'foo-noo-baz'])
        self.assertEqual(converted, {
            'foo-bar': {'baz', 'qux'},
            'foo-noo': {'baz'},
            })

    def test_terminate_instances_one_role(self):
        client = make_sms(['foo-bar'])
        account = AzureAccount(client)
        account.terminate_instances(['foo-bar'])
        client.delete_deployment.assert_called_once_with('foo', 'foo-v3')
        client.delete_hosted_service.assert_called_once_with('foo')

    def test_terminate_instances_not_all_roles(self):
        client = make_sms(['foo-bar', 'foo-baz', 'foo-qux'])
        account = AzureAccount(client)
        account.terminate_instances(['foo-bar', 'foo-baz'])
        client.get_hosted_service_properties.assert_called_once_with(
            'foo', embed_detail=True)
        self.assertItemsEqual(client.delete_role.mock_calls, [
            call('foo', 'foo-v3', 'bar'),
            call('foo', 'foo-v3', 'baz'),
            ])
        self.assertEqual(client.delete_deployment.call_count, 0)
        self.assertEqual(client.delete_hosted_service.call_count, 0)

    def test_terminate_instances_all_roles(self):
        client = make_sms(['foo-bar', 'foo-baz', 'foo-qux'])
        account = AzureAccount(client)
        account.terminate_instances(['foo-bar', 'foo-baz', 'foo-qux'])
        client.get_hosted_service_properties.assert_called_once_with(
            'foo', embed_detail=True)
        client.delete_deployment.assert_called_once_with('foo', 'foo-v3')
        client.delete_hosted_service.assert_called_once_with('foo')


def get_azure_credentials():
    return {
        'subscription-id': 'subscription-id',
        'application-id': 'application-id',
        'application-password': 'application-password',
    }


def get_azure_config():
    config = {
        'type': 'azure',
        'tenant-id': 'tenant-id'
    }
    config.update(get_azure_credentials())
    return config


class TestAzureARMAccount(TestCase):

    @patch('winazurearm.ARMClient.init_services',
           autospec=True, side_effect=fake_init_services)
    def test_from_boot_config(self, is_mock):
        boot_config = SimpleEnvironment('foo', get_azure_config())
        with AzureARMAccount.from_boot_config(boot_config) as substrate:
            self.assertEqual(
                substrate.arm_client.subscription_id, 'subscription-id')
            self.assertEqual(substrate.arm_client.client_id, 'application-id')
            self.assertEqual(
                substrate.arm_client.secret, 'application-password')
            self.assertEqual(substrate.arm_client.tenant, 'tenant-id')
            is_mock.assert_called_once_with(substrate.arm_client)

    @patch('winazurearm.ARMClient.init_services',
           autospec=True, side_effect=fake_init_services)
    def test_terminate_instances(self, is_mock):
        config = get_azure_config()
        arm_client = ARMClient(
            config['subscription-id'], config['application-id'],
            config['application-password'], config['tenant-id'])
        account = AzureARMAccount(arm_client)
        with patch('winazurearm.delete_instance', autospec=True) as di_mock:
            account.terminate_instances(['foo-bar'])
        di_mock.assert_called_once_with(
            arm_client, 'foo-bar', resource_group=None)

    @patch('winazurearm.ARMClient.init_services',
           autospec=True, side_effect=fake_init_services)
    def test_convert_to_azure_ids(self, is_mock):
        env = JujuData('controller', get_azure_config(), juju_home='data')
        client = fake_juju_client(env=env)

        arm_client = ARMClient(
            'subscription-id', 'application-id', 'application-password',
            'tenant-id')
        account = AzureARMAccount(arm_client)
        group = ResourceGroup(name='juju-controller-model-bar')
        virtual_machine = VirtualMachine('machine-0', 'abcd-1234')
        other_machine = VirtualMachine('machine-1', 'bcde-1234')
        fake_listed = [ResourceGroupDetails(
            arm_client, group, vms=[virtual_machine, other_machine])]
        models = {'models': [
            {'name': 'controller',
                'model-uuid': 'bar', 'controller-uuid': 'bar'},
            {'name': 'default',
                'model-uuid': 'baz', 'controller-uuid': 'bar'},
            ]}
        with patch.object(client, 'get_models', autospec=True,
                          return_value=models) as gm_mock:
            with patch('winazurearm.list_resources', autospec=True,
                       return_value=fake_listed) as lr_mock:
                ids = account.convert_to_azure_ids(client, ['machine-0'])
        self.assertEqual(['abcd-1234'], ids)
        gm_mock.assert_called_once_with()
        lr_mock.assert_called_once_with(
            arm_client, glob='juju-controller-model-bar', recursive=True)

    @patch('winazurearm.ARMClient.init_services',
           autospec=True, side_effect=fake_init_services)
    def test_convert_to_azure_ids_function(self, is_mock):
        env = JujuData('controller', get_azure_config(), juju_home='data')
        env.credentials['credentials'] = {'azure': {
            'credentials': get_azure_credentials()
            }}
        client = fake_juju_client(env=env)
        arm_client = ARMClient(
            'subscription-id', 'application-id', 'application-password',
            'tenant-id')
        group = ResourceGroup(name='juju-controller-model-bar')
        virtual_machine = VirtualMachine('machine-0', 'abcd-1234')
        other_machine = VirtualMachine('machine-1', 'bcde-1234')
        fake_listed = [ResourceGroupDetails(
            arm_client, group, vms=[virtual_machine, other_machine])]
        models = {'models': [
            {'name': 'controller',
                'model-uuid': 'bar', 'controller-uuid': 'bar'},
            {'name': 'default',
                'model-uuid': 'baz', 'controller-uuid': 'bar'},
            ]}
        with patch.object(client, 'get_models', autospec=True,
                          return_value=models) as gm_mock:
            with patch('winazurearm.list_resources', autospec=True,
                       return_value=fake_listed) as lr_mock:
                ids = convert_to_azure_ids(client, ['machine-0'])
        self.assertEqual(['abcd-1234'], ids)
        gm_mock.assert_called_once_with()
        lr_mock.assert_called_once_with(
            arm_client, glob='juju-controller-model-bar', recursive=True)

    def test_convert_to_azure_ids_function_1x_client(self):
        env = SimpleEnvironment('foo', config=get_azure_config())
        client = fake_juju_client(env=env, version='1.2', cls=EnvJujuClient1X)
        with patch.object(client, 'get_models') as gm_mock:
            with patch('winazurearm.list_resources') as lr_mock:
                ids = convert_to_azure_ids(client, ['a-sensible-id'])
        self.assertEqual(['a-sensible-id'], ids)
        self.assertEqual(0, gm_mock.call_count)
        self.assertEqual(0, lr_mock.call_count)

    @patch('winazurearm.ARMClient.init_services',
           autospec=True, side_effect=fake_init_services)
    def test_convert_to_azure_ids_function_bug_1586089_fixed(self, is_mock):
        env = JujuData('controller', get_azure_config(), juju_home='data')
        env.credentials['credentials'] = {'azure': {
            'credentials': get_azure_credentials()
            }}
        client = fake_juju_client(env=env, version='2.1')
        with patch.object(client, 'get_models') as gm_mock:
            with patch('winazurearm.list_resources') as lr_mock:
                ids = convert_to_azure_ids(client, ['a-sensible-id'])
        self.assertEqual(['a-sensible-id'], ids)
        self.assertEqual(0, gm_mock.call_count)
        self.assertEqual(0, lr_mock.call_count)


class TestMAASAccount(TestCase):

    def get_account(self):
        """Give a MAASAccount for testing."""
        boot_config = get_maas_env()
        return MAASAccount(
            boot_config.get_option('name'),
            boot_config.get_option('maas-server'),
            boot_config.get_option('maas-oauth'),
            )

    @patch('subprocess.check_call', autospec=True)
    def test_login(self, cc_mock):
        account = self.get_account()
        account.login()
        cc_mock.assert_called_once_with([
            'maas', 'login', 'mas', 'http://10.0.10.10/MAAS/api/2.0/',
            'a:password:string'])

    @patch('subprocess.check_call', autospec=True)
    def test_logout(self, cc_mock):
        account = self.get_account()
        account.logout()
        cc_mock.assert_called_once_with(['maas', 'logout', 'mas'])

    def test_terminate_instances(self):
        account = self.get_account()
        instance_ids = ['/A/B/C/D/node-1d/', '/A/B/C/D/node-2d/']
        with patch('subprocess.check_output', autospec=True,
                   return_value='{}') as co_mock:
            account.terminate_instances(instance_ids)
        co_mock.assert_any_call(
            ('maas', 'mas', 'machine', 'release', 'node-1d'))
        co_mock.assert_called_with(
            ('maas', 'mas', 'machine', 'release', 'node-2d'))

    def test_get_allocated_nodes(self):
        account = self.get_account()
        node = make_maas_node('maas-node-1.maas')
        allocated_nodes_string = '[%s]' % json.dumps(node)
        with patch('subprocess.check_output', autospec=True,
                   return_value=allocated_nodes_string) as co_mock:
            allocated = account.get_allocated_nodes()
        co_mock.assert_called_once_with(
            ('maas', 'mas', 'machines', 'list-allocated'))
        self.assertEqual(node, allocated['maas-node-1.maas'])

    def make_event(self, acquire_date, type_=MAASAccount.ACQUIRING):
        return {
            'type': type_,
            MAASAccount.CREATED: acquire_date.isoformat(),
            MAASAccount.NODE: 'asdf',
            }

    def test_get_acquire_date(self):
        acquire_date = datetime(2016, 10, 25)
        result = self._run_acquire_date(acquire_date)
        self.assertEqual(acquire_date, result)

    def _run_acquire_date(self, acquire_date, type_=MAASAccount.ACQUIRING,
                          node='asdf'):
        events = {'events': [
            self.make_event(acquire_date, type_=type_),
            ]}
        return self._run_acquire_date_events(events, node)

    def _run_acquire_date_events(self, events, node):
        account = self.get_account()
        with patch('subprocess.check_output', autospec=True,
                   return_value=json.dumps(events)) as co_mock:
            result = account.get_acquire_date(node)
        co_mock.assert_called_once_with(
            ('maas', 'mas', 'events', 'query', 'id={}'.format(node)))
        return result

    def test_get_acquire_date_not_acquiring(self):
        acquire_date = datetime(2016, 10, 25)
        with self.assertRaisesRegexp(
                LookupError, 'Unable to find acquire date for "asdf".'):
            self._run_acquire_date(acquire_date, type_='Not acquiring')

    def test_get_acquire_date_uses_first_entry(self):
        acquire_date = datetime(2016, 10, 25)
        newer_date = datetime(2016, 10, 26)
        older_date = datetime(2016, 10, 24)
        events = {'events': [
            self.make_event(acquire_date),
            self.make_event(older_date),
            self.make_event(newer_date),
            ]}
        result = self._run_acquire_date_events(events, 'asdf')
        self.assertEqual(acquire_date, result)

    def test_get_acquire_date_wrong_node(self):
        acquire_date = datetime(2016, 10, 25)
        with self.assertRaisesRegexp(ValueError, 'Node "asdf" was not "fasd"'):
            self._run_acquire_date(acquire_date, node='fasd')

    def test_get_allocated_ips(self):
        account = self.get_account()
        node = make_maas_node('maas-node-1.maas')
        allocated_nodes_string = '[%s]' % json.dumps(node)
        with patch('subprocess.check_output', autospec=True,
                   return_value=allocated_nodes_string) as co_mock:
            ips = account.get_allocated_ips()
        co_mock.assert_called_once_with(
            ('maas', 'mas', 'machines', 'list-allocated'))
        self.assertEqual('10.0.30.165', ips['maas-node-1.maas'])

    def test_get_allocated_ips_empty(self):
        account = self.get_account()
        node = make_maas_node('maas-node-1.maas')
        node['ip_addresses'] = []
        allocated_nodes_string = '[%s]' % json.dumps(node)
        with patch('subprocess.check_output', autospec=True,
                   return_value=allocated_nodes_string) as co_mock:
            ips = account.get_allocated_ips()
        co_mock.assert_called_once_with(
            ('maas', 'mas', 'machines', 'list-allocated'))
        self.assertEqual({}, ips)

    def test_machines(self):
        account = self.get_account()
        with patch('subprocess.check_output', autospec=True,
                   return_value='[]') as co_mock:
            machines = account.machines()
        co_mock.assert_called_once_with(('maas', 'mas', 'machines', 'read'))
        self.assertEqual([], machines)

    def test_fabrics(self):
        account = self.get_account()
        with patch('subprocess.check_output', autospec=True,
                   return_value='[]') as co_mock:
            fabrics = account.fabrics()
        co_mock.assert_called_once_with(('maas', 'mas', 'fabrics', 'read'))
        self.assertEqual([], fabrics)

    def test_create_fabric(self):
        account = self.get_account()
        with patch('subprocess.check_output', autospec=True,
                   return_value='{"id": 1}') as co_mock:
            fabric = account.create_fabric('a-fabric')
            co_mock.assert_called_once_with((
                'maas', 'mas', 'fabrics', 'create', 'name=a-fabric'))
            self.assertEqual({'id': 1}, fabric)
            co_mock.reset_mock()
            fabric = account.create_fabric('a-fabric', class_type='something')
            co_mock.assert_called_once_with((
                'maas', 'mas', 'fabrics', 'create', 'name=a-fabric',
                'class_type=something'))
            self.assertEqual({'id': 1}, fabric)

    def test_delete_fabric(self):
        account = self.get_account()
        with patch('subprocess.check_output', autospec=True,
                   return_value='') as co_mock:
            result = account.delete_fabric(1)
        co_mock.assert_called_once_with(
            ('maas', 'mas', 'fabric', 'delete', '1'))
        self.assertEqual(None, result)

    def test_spaces(self):
        account = self.get_account()
        with patch('subprocess.check_output', autospec=True,
                   return_value='[]') as co_mock:
            spaces = account.spaces()
        co_mock.assert_called_once_with(('maas', 'mas', 'spaces', 'read'))
        self.assertEqual([], spaces)

    def test_create_space(self):
        account = self.get_account()
        with patch('subprocess.check_output', autospec=True,
                   return_value='{"id": 1}') as co_mock:
            fabric = account.create_space('a-space')
        co_mock.assert_called_once_with((
            'maas', 'mas', 'spaces', 'create', 'name=a-space'))
        self.assertEqual({'id': 1}, fabric)

    def test_delete_space(self):
        account = self.get_account()
        with patch('subprocess.check_output', autospec=True,
                   return_value='') as co_mock:
            result = account.delete_space(1)
        co_mock.assert_called_once_with(
            ('maas', 'mas', 'space', 'delete', '1'))
        self.assertEqual(None, result)

    def test_create_vlan(self):
        account = self.get_account()
        with patch('subprocess.check_output', autospec=True,
                   return_value='{"id": 5000}') as co_mock:
            vlan = account.create_vlan(0, 1)
            co_mock.assert_called_once_with((
                'maas', 'mas', 'vlans', 'create', '0', 'vid=1'))
            self.assertEqual({'id': 5000}, vlan)
            co_mock.reset_mock()
            vlan = account.create_vlan(1, 2, name='a-vlan')
            co_mock.assert_called_once_with((
                'maas', 'mas', 'vlans', 'create', '1', 'vid=2', 'name=a-vlan'))
            self.assertEqual({'id': 5000}, vlan)

    def test_delete_vlan(self):
        account = self.get_account()
        with patch('subprocess.check_output', autospec=True,
                   return_value='') as co_mock:
            result = account.delete_vlan(0, 4096)
        co_mock.assert_called_once_with(
            ('maas', 'mas', 'vlan', 'delete', '0', '4096'))
        self.assertEqual(None, result)

    def test_interfaces(self):
        account = self.get_account()
        with patch('subprocess.check_output', autospec=True,
                   return_value='[]') as co_mock:
            interfaces = account.interfaces('node-xyz')
        co_mock.assert_called_once_with((
            'maas', 'mas', 'interfaces', 'read', 'node-xyz'))
        self.assertEqual([], interfaces)

    def test_interface_update(self):
        account = self.get_account()
        with patch('subprocess.check_output', autospec=True,
                   return_value='{"id": 10}') as co_mock:
            interface = account.interface_update('node-xyz', 10, vlan_id=5000)
        co_mock.assert_called_once_with((
            'maas', 'mas', 'interface', 'update', 'node-xyz', '10',
            'vlan=5000'))
        self.assertEqual({'id': 10}, interface)

    def test_interface_create_vlan(self):
        account = self.get_account()
        with patch('subprocess.check_output', autospec=True,
                   return_value='{"id": 10}') as co_mock:
            interface = account.interface_create_vlan('node-xyz', 1, 5000)
        co_mock.assert_called_once_with((
            'maas', 'mas', 'interfaces', 'create-vlan', 'node-xyz', 'parent=1',
            'vlan=5000'))
        self.assertEqual({'id': 10}, interface)

    def test_delete_interface(self):
        account = self.get_account()
        with patch('subprocess.check_output', autospec=True,
                   return_value='') as co_mock:
            result = account.delete_interface('node-xyz', 10)
        co_mock.assert_called_once_with(
            ('maas', 'mas', 'interface', 'delete', 'node-xyz', '10'))
        self.assertEqual(None, result)

    def test_interface_link_subnet(self):
        account = self.get_account()
        with patch('subprocess.check_output', autospec=True,
                   return_value='{"id": 10}') as co_mock:
            subnet = account.interface_link_subnet('node-xyz', 10, 'AUTO', 40)
            co_mock.assert_called_once_with((
                'maas', 'mas', 'interface', 'link-subnet', 'node-xyz', '10',
                'mode=AUTO', 'subnet=40'))
            self.assertEqual({'id': 10}, subnet)
            co_mock.reset_mock()
            subnet = account.interface_link_subnet(
                'node-xyz', 10, 'STATIC', 40, ip_address='10.0.10.2',
                default_gateway=True)
            co_mock.assert_called_once_with((
                'maas', 'mas', 'interface', 'link-subnet', 'node-xyz', '10',
                'mode=STATIC', 'subnet=40', 'ip_address=10.0.10.2',
                'default_gateway=true'))
            self.assertEqual({'id': 10}, subnet)

    def test_interface_link_subnet_invalid(self):
        account = self.get_account()
        with patch('subprocess.check_output', autospec=True,
                   return_value='') as co_mock:
            err_pattern = '^Invalid subnet connection mode: MAGIC$'
            with self.assertRaisesRegexp(ValueError, err_pattern):
                account.interface_link_subnet('node-xyz', 10, 'MAGIC', 40)
            err_pattern = '^Must be mode STATIC for ip_address$'
            with self.assertRaisesRegexp(ValueError, err_pattern):
                account.interface_link_subnet(
                    'node-xyz', 10, 'AUTO', 40, ip_address='127.0.0.1')
            err_pattern = '^Must be mode AUTO or STATIC for default_gateway$'
            with self.assertRaisesRegexp(ValueError, err_pattern):
                account.interface_link_subnet(
                    'node-xyz', 10, 'LINK_UP', 40, default_gateway=True)
        self.assertEqual(0, co_mock.call_count)

    def test_interface_unlink_subnet(self):
        account = self.get_account()
        with patch('subprocess.check_output', autospec=True,
                   return_value='') as co_mock:
            result = account.interface_unlink_subnet('node-xyz', 10, 20000)
        co_mock.assert_called_once_with((
            'maas', 'mas', 'interface', 'unlink-subnet', 'node-xyz', '10',
            'id=20000'))
        self.assertEqual(None, result)

    def test_subnets(self):
        account = self.get_account()
        with patch('subprocess.check_output', autospec=True,
                   return_value='[]') as co_mock:
            subnets = account.subnets()
        co_mock.assert_called_once_with(('maas', 'mas', 'subnets', 'read'))
        self.assertEqual([], subnets)

    def test_create_subnet(self):
        account = self.get_account()
        with patch('subprocess.check_output', autospec=True,
                   return_value='{"id": 1}') as co_mock:
            subnet = account.create_subnet('10.0.0.0/24')
            co_mock.assert_called_once_with((
                'maas', 'mas', 'subnets', 'create', 'cidr=10.0.0.0/24'))
            self.assertEqual({'id': 1}, subnet)
            co_mock.reset_mock()
            subnet = account.create_subnet(
                '10.10.0.0/24', name='test-subnet', fabric_id='1', vlan_id='5',
                space='2', gateway_ip='10.10.0.1')
            co_mock.assert_called_once_with((
                'maas', 'mas', 'subnets', 'create', 'cidr=10.10.0.0/24',
                'name=test-subnet', 'fabric=1', 'vlan=5', 'space=2',
                'gateway_ip=10.10.0.1'))
            self.assertEqual({'id': 1}, subnet)
            co_mock.reset_mock()
            subnet = account.create_subnet(
                '10.10.0.0/24', name='test-subnet', fabric_id='1', vid='0',
                space='2', dns_servers='8.8.8.8,8.8.4.4')
            co_mock.assert_called_once_with((
                'maas', 'mas', 'subnets', 'create', 'cidr=10.10.0.0/24',
                'name=test-subnet', 'fabric=1', 'vid=0', 'space=2',
                'dns_servers=8.8.8.8,8.8.4.4'))
            self.assertEqual({'id': 1}, subnet)

    def test_create_subnet_invalid(self):
        account = self.get_account()
        with patch('subprocess.check_output', autospec=True,
                   return_value='') as co_mock:
            err_pattern = '^Must only give one of vlan_id and vid$'
            with self.assertRaisesRegexp(ValueError, err_pattern):
                account.create_subnet('10.0.0.0/24', vlan_id=10, vid=1)
        self.assertEqual(0, co_mock.call_count)

    def test_delete_subnet(self):
        account = self.get_account()
        with patch('subprocess.check_output', autospec=True,
                   return_value='') as co_mock:
            result = account.delete_subnet(1)
        co_mock.assert_called_once_with(
            ('maas', 'mas', 'subnet', 'delete', '1'))
        self.assertEqual(None, result)


class TestMAAS1Account(TestCase):

    def get_account(self):
        """Give a MAAS1Account for testing."""
        boot_config = get_maas_env()
        return MAAS1Account(
            boot_config.get_option('name'),
            boot_config.get_option('maas-server'),
            boot_config.get_option('maas-oauth'),
            )

    @patch('subprocess.check_call', autospec=True)
    def test_login(self, cc_mock):
        account = self.get_account()
        account.login()
        cc_mock.assert_called_once_with([
            'maas', 'login', 'mas', 'http://10.0.10.10/MAAS/api/1.0/',
            'a:password:string'])

    @patch('subprocess.check_call', autospec=True)
    def test_logout(self, cc_mock):
        account = self.get_account()
        account.logout()
        cc_mock.assert_called_once_with(['maas', 'logout', 'mas'])

    def test_terminate_instances(self):
        account = self.get_account()
        instance_ids = ['/A/B/C/D/node-1d/', '/A/B/C/D/node-2d/']
        with patch('subprocess.check_output', autospec=True,
                   return_value='{}') as co_mock:
            account.terminate_instances(instance_ids)
        co_mock.assert_any_call(
            ('maas', 'mas', 'node', 'release', 'node-1d'))
        co_mock.assert_called_with(
            ('maas', 'mas', 'node', 'release', 'node-2d'))

    def test_get_allocated_nodes(self):
        account = self.get_account()
        node = make_maas_node('maas-node-1.maas')
        allocated_nodes_string = '[%s]' % json.dumps(node)
        with patch('subprocess.check_output', autospec=True,
                   return_value=allocated_nodes_string) as co_mock:
            allocated = account.get_allocated_nodes()
        co_mock.assert_called_once_with(
            ('maas', 'mas', 'nodes', 'list-allocated'))
        self.assertEqual(node, allocated['maas-node-1.maas'])

    def test_get_allocated_ips(self):
        account = self.get_account()
        node = make_maas_node('maas-node-1.maas')
        allocated_nodes_string = '[%s]' % json.dumps(node)
        with patch('subprocess.check_output', autospec=True,
                   return_value=allocated_nodes_string) as co_mock:
            ips = account.get_allocated_ips()
        co_mock.assert_called_once_with(
            ('maas', 'mas', 'nodes', 'list-allocated'))
        self.assertEqual('10.0.30.165', ips['maas-node-1.maas'])

    def test_get_allocated_ips_empty(self):
        account = self.get_account()
        node = make_maas_node('maas-node-1.maas')
        node['ip_addresses'] = []
        allocated_nodes_string = '[%s]' % json.dumps(node)
        with patch('subprocess.check_output', autospec=True,
                   return_value=allocated_nodes_string) as co_mock:
            ips = account.get_allocated_ips()
        co_mock.assert_called_once_with(
            ('maas', 'mas', 'nodes', 'list-allocated'))
        self.assertEqual({}, ips)


class TestMAASAccountFromConfig(TestCase):

    def test_login_succeeds(self):
        boot_config = get_maas_env()
        with patch('subprocess.check_call', autospec=True) as cc_mock:
            with maas_account_from_boot_config(boot_config) as maas:
                self.assertIs(type(maas), MAASAccount)
                self.assertEqual(maas.profile, 'mas')
                self.assertEqual(maas.url, 'http://10.0.10.10/MAAS/api/2.0/')
                self.assertEqual(maas.oauth, 'a:password:string')
                cc_mock.assert_called_once_with([
                    'maas', 'login', 'mas', 'http://10.0.10.10/MAAS/api/2.0/',
                    'a:password:string'])

    def test_login_fallback(self):
        boot_config = get_maas_env()
        login_error = CalledProcessError(1, ['maas', 'login'])
        with patch('subprocess.check_call', autospec=True,
                   side_effect=[login_error, None, None]) as cc_mock:
            with maas_account_from_boot_config(boot_config) as maas:
                self.assertIs(type(maas), MAAS1Account)
                self.assertEqual(maas.profile, 'mas')
                self.assertEqual(maas.url, 'http://10.0.10.10/MAAS/api/1.0/')
                self.assertEqual(maas.oauth, 'a:password:string')
                # The first login attempt was with the 2.0 api, after which
                # a 1.0 login succeeded.
                self.assertEquals(cc_mock.call_args_list, [
                    call(['maas', 'login', 'mas',
                          'http://10.0.10.10/MAAS/api/2.0/',
                          'a:password:string']),
                    call(['maas', 'login', 'mas',
                          'http://10.0.10.10/MAAS/api/1.0/',
                          'a:password:string']),
                ])
        self.assertEqual(
            self.log_stream.getvalue(),
            'INFO Could not login with MAAS 2.0 API, trying 1.0\n')

    def test_login_both_fail(self):
        boot_config = get_maas_env()
        login_error = CalledProcessError(1, ['maas', 'login'])
        with patch('subprocess.check_call', autospec=True,
                   side_effect=login_error) as cc_mock:
            with self.assertRaises(CalledProcessError) as ctx:
                with maas_account_from_boot_config(boot_config):
                    self.fail('Should never get manager with failed login')
        self.assertIs(ctx.exception, login_error)
        self.assertEquals(cc_mock.call_args_list, [
            call(['maas', 'login', 'mas',
                  'http://10.0.10.10/MAAS/api/2.0/',
                  'a:password:string']),
            call(['maas', 'login', 'mas',
                  'http://10.0.10.10/MAAS/api/1.0/',
                  'a:password:string']),
        ])
        self.assertEqual(
            self.log_stream.getvalue(),
            'INFO Could not login with MAAS 2.0 API, trying 1.0\n')

    def test_login_uses_cloud_credentials(self):
        boot_config = get_maas_boot_config()
        with patch('subprocess.check_call', autospec=True) as cc_mock:
            with maas_account_from_boot_config(boot_config) as maas:
                self.assertIs(type(maas), MAASAccount)
                self.assertEqual(maas.profile, 'mas')
                self.assertEqual(maas.url, 'http://10.0.10.10/MAAS/api/2.0/')
                self.assertEqual(maas.oauth, 'a:password:string')
                cc_mock.assert_called_once_with([
                    'maas', 'login', 'mas', 'http://10.0.10.10/MAAS/api/2.0/',
                    'a:password:string'])


class TestMakeSubstrateManager(FakeHomeTestCase):

    def test_make_substrate_manager_aws(self):
        boot_config = get_aws_env()
        with patch('substrate.ec2.connect_to_region', autospec=True):
            with make_substrate_manager(boot_config) as aws:
                self.assertIs(type(aws), AWSAccount)
                self.assertEqual(aws.euca_environ, {
                    'AWS_ACCESS_KEY': 'skeleton-key',
                    'AWS_SECRET_KEY': 'secret-skeleton-key',
                    'EC2_ACCESS_KEY': 'skeleton-key',
                    'EC2_SECRET_KEY': 'secret-skeleton-key',
                    'EC2_URL': 'https://ca-west.ec2.amazonaws.com',
                    })
                self.assertEqual(aws.region, 'ca-west')

    def test_make_substrate_manager_openstack(self):
        boot_config = get_os_boot_config()
        with make_substrate_manager(boot_config) as account:
            self.assertIs(type(account), OpenStackAccount)
            self.assertEqual(account._username, 'foo')
            self.assertEqual(account._password, 'bar')
            self.assertEqual(account._tenant_name, 'baz')
            self.assertEqual(account._auth_url, 'qux')
            self.assertEqual(account._region_name, 'quxx')

    def test_make_substrate_manager_rackspace(self):
        config = get_os_config()
        config['type'] = 'rackspace'
        boot_config = SimpleEnvironment('foo', config)
        with make_substrate_manager(boot_config) as account:
            self.assertIs(type(account), OpenStackAccount)
            self.assertEqual(account._username, 'foo')
            self.assertEqual(account._password, 'bar')
            self.assertEqual(account._tenant_name, 'baz')
            self.assertEqual(account._auth_url, 'qux')
            self.assertEqual(account._region_name, 'quxx')

    def test_make_substrate_manager_joyent(self):
        boot_config = SimpleEnvironment('foo', get_joyent_config())
        with make_substrate_manager(boot_config) as account:
            self.assertEqual(account.client.sdc_url, 'http://example.org/sdc')
            self.assertEqual(account.client.account, 'user@manta.org')
            self.assertEqual(account.client.key_id, 'key-id@manta.org')

    def test_make_substrate_manager_azure(self):
        boot_config = SimpleEnvironment('foo', {
            'type': 'azure',
            'management-subscription-id': 'fooasdfbar',
            'management-certificate': 'ab\ncd\n'
            })
        with make_substrate_manager(boot_config) as substrate:
            self.assertIs(type(substrate), AzureAccount)
            self.assertEqual(substrate.service_client.subscription_id,
                             'fooasdfbar')
            self.assertEqual(open(substrate.service_client.cert_file).read(),
                             'ab\ncd\n')
        self.assertFalse(os.path.exists(substrate.service_client.cert_file))

    @patch('winazurearm.ARMClient.init_services',
           autospec=True, side_effect=fake_init_services)
    def test_make_substrate_manager_azure_arm(self, is_mock):
        boot_config = SimpleEnvironment('foo', get_azure_config())
        with make_substrate_manager(boot_config) as substrate:
            self.assertEqual(
                substrate.arm_client.subscription_id, 'subscription-id')
            self.assertEqual(
                substrate.arm_client.client_id, 'application-id')
            self.assertEqual(
                substrate.arm_client.secret, 'application-password')
            self.assertEqual(substrate.arm_client.tenant, 'tenant-id')
            is_mock.assert_called_once_with(substrate.arm_client)

    def test_make_substrate_manager_gce(self):
        boot_config = JujuData('foo', get_gce_config())
        boot_config.credentials['credentials'] = {'google': {'baz': {}}}
        client = test_gce.make_fake_client()
        with patch('gce.get_client',
                   autospec=True, return_value=client) as gc_mock:
            with make_substrate_manager(boot_config) as account:
                self.assertIs(client, account.client)
        args = gc_mock.call_args[0]
        self.assertEqual('me@serviceaccount.google.com', args[0])
        self.assertIsTrue(args[1].endswith('gce.pem'))
        self.assertEqual('test-project', args[2])

    def test_make_substrate_manager_other(self):
        config = get_os_config()
        config['type'] = 'other'
        boot_config = SimpleEnvironment('foo', config)
        with make_substrate_manager(boot_config) as account:
            self.assertIs(account, None)

    def test_get_config_lxd(self):
        boot_config = get_lxd_config()
        env = JujuData('foo', boot_config)
        config = get_config(env)
        self.assertEqual(boot_config, config)

    def test_get_config_manual(self):
        boot_config = {'type': 'manual'}
        env = JujuData('foo', boot_config)
        config = get_config(env)
        self.assertEqual(boot_config, config)


class TestLibvirt(TestCase):

    def test_start_libvirt_domain(self):
        uri = 'qemu+ssh://someHost/system'
        dom_name = 'fido'
        with patch('subprocess.check_output',
                   return_value='running') as mock_sp:
            with patch('substrate.sleep'):
                start_libvirt_domain(uri, dom_name)
        mock_sp.assert_any_call(['virsh', '-c', uri, 'start', dom_name],
                                stderr=ANY)

    def test_stop_libvirt_domain(self):
        uri = 'qemu+ssh://someHost/system'
        dom_name = 'fido'
        with patch('subprocess.check_output',
                   return_value='shut off') as mock_sp:
            with patch('substrate.sleep'):
                stop_libvirt_domain(uri, dom_name)
        mock_sp.assert_any_call(['virsh', '-c', uri, 'shutdown', dom_name],
                                stderr=ANY)

    def test_get_libvirt_domstate(self):
        uri = 'qemu+ssh://someHost/system'
        dom_name = 'fido'
        expected_cmd = ['virsh', '-c', uri, 'domstate', dom_name]
        with patch('subprocess.check_output') as m_sub:
            get_libvirt_domstate(uri, dom_name)
        m_sub.assert_called_with(expected_cmd)

    def test_verify_libvirt_domain_shut_off_true(self):
        uri = 'qemu+ssh://someHost/system'
        dom_name = 'fido'
        with patch('substrate.get_libvirt_domstate', return_value='shut off'):
            rval = verify_libvirt_domain(uri, dom_name, 'shut off')
        self.assertTrue(rval)

    def test_verify_libvirt_domain_shut_off_false(self):
        uri = 'qemu+ssh://someHost/system'
        dom_name = 'fido'
        with patch('substrate.get_libvirt_domstate', return_value='running'):
            rval = verify_libvirt_domain(uri, dom_name, 'shut off')
        self.assertFalse(rval)

    def test_verify_libvirt_domain_running_true(self):
        uri = 'qemu+ssh://someHost/system'
        dom_name = 'fido'
        with patch('substrate.get_libvirt_domstate', return_value='running'):
            rval = verify_libvirt_domain(uri, dom_name, 'running')
        self.assertTrue(rval)

    def test_verify_libvirt_domain_running_false(self):
        uri = 'qemu+ssh://someHost/system'
        dom_name = 'fido'
        with patch('substrate.get_libvirt_domstate', return_value='shut off'):
            rval = verify_libvirt_domain(uri, dom_name, 'running')
        self.assertFalse(rval)


class TestHasNovaInstance(TestCase):

    def run_has_nova_instance(self, return_value=''):
        boot_config = JujuData('foo', {
            'type': 'openstack',
            'region': 'lcy05',
            'username': 'steve',
            'password': 'password1',
            'tenant-name': 'steven',
            'auth-url': 'http://example.org',
            }, 'home')
        with patch('subprocess.check_output', autospec=True,
                   return_value=return_value) as co_mock:
            result = has_nova_instance(boot_config, 'i-255')
        environ = dict(os.environ)
        environ.update({
            'OS_AUTH_URL': 'http://example.org',
            'OS_USERNAME': 'steve',
            'OS_PASSWORD': 'password1',
            'OS_REGION_NAME': 'lcy05',
            'OS_TENANT_NAME': 'steven',
            })
        co_mock.assert_called_once_with(['nova', 'list'], env=environ)
        return result

    def test_has_nova_instance_false(self):
        self.assertIs(False, self.run_has_nova_instance())

    def test_has_nova_instance_true(self):
        self.assertIs(True, self.run_has_nova_instance('i-255'))


class EucaTestCase(TestCase):

    def test_get_job_instances_none(self):
        with patch('substrate.describe_instances',
                   return_value=[], autospec=True) as di_mock:
            ids = get_job_instances('foo')
        self.assertEqual([], [i for i in ids])
        di_mock.assert_called_with(job_name='foo', running=True)

    def test_get_job_instances_some(self):
        description = ('i-bar', 'foo-0')
        with patch('substrate.describe_instances',
                   return_value=[description], autospec=True) as di_mock:
            ids = get_job_instances('foo')
        self.assertEqual(['i-bar'], [i for i in ids])
        di_mock.assert_called_with(job_name='foo', running=True)

    def test_describe_instances(self):
        with patch('subprocess.check_output',
                   return_value='', autospec=True) as co_mock:
            with patch('substrate.parse_euca', autospec=True) as pe_mock:
                describe_instances(
                    instances=['i-foo'], job_name='bar', running=True)
        co_mock.assert_called_with(
            ['euca-describe-instances',
             '--filter', 'tag:job_name=bar',
             '--filter', 'instance-state-name=running',
             'i-foo'], env=None)
        pe_mock.assert_called_with('')

    def test_parse_euca(self):
        description = parse_euca('')
        self.assertEqual([], [d for d in description])
        euca_data = dedent("""
            header
            INSTANCE\ti-foo\tblah\tbar-0
            INSTANCE\ti-baz\tblah\tbar-1
        """)
        description = parse_euca(euca_data)
        self.assertEqual(
            [('i-foo', 'bar-0'), ('i-baz', 'bar-1')], [d for d in description])

    def test_destroy_job_instances_none(self):
        with patch('substrate.get_job_instances',
                   return_value=[], autospec=True) as gji_mock:
            with patch('subprocess.check_call') as cc_mock:
                destroy_job_instances('foo')
        gji_mock.assert_called_with('foo')
        self.assertEqual(0, cc_mock.call_count)

    def test_destroy_job_instances_some(self):
        with patch('substrate.get_job_instances',
                   return_value=['i-bar'], autospec=True) as gji_mock:
            with patch('subprocess.check_call') as cc_mock:
                destroy_job_instances('foo')
        gji_mock.assert_called_with('foo')
        cc_mock.assert_called_with(['euca-terminate-instances', 'i-bar'])


class TestEnsureCleanup(TestCase):
    def test_lxd_ensure_cleanup(self):
        substrate_account = LXDAccount()
        self.assertEqual([], substrate_account.ensure_cleanup([]))

    def test_aws_ensure_cleanup(self):
        substrate_account = AWSAccount('euca_environ', 'region', 'client')
        self.assertEqual([], substrate_account.ensure_cleanup([]))

    def test_openstack_ensure_cleanup(self):
        substrate_account = OpenStackAccount(
            'username', 'password', 'tenant_name', 'auth_url', 'region_name')
        self.assertEqual([], substrate_account.ensure_cleanup([]))

    def test_rax_ensure_cleanup(self):
        substrate_account = JoyentAccount('client')
        self.assertEqual([], substrate_account.ensure_cleanup([]))

    def test_gce_ensure_cleanup(self):
        substrate_account = GCEAccount('client')
        self.assertEqual([], substrate_account.ensure_cleanup([]))

    def test_maas_ensure_cleanup(self):
        substrate_account = MAASAccount('profile', 'url', 'oauth')
        self.assertEqual([], substrate_account.ensure_cleanup([]))


class FakeSecurityGroup:
    def __init__(self, id, instances):
        self.id = id
        self._instances = instances

    def instances(self):
        return self._instances


class TestAWSEnsureCleanUp(TestCase):
    def test_ensure_cleanup_successfully(self):
        client = MagicMock()
        resource_details = dict()
        resource_details['instances'] = ["i_id1", "i_id2"]
        aws = AWSAccount(None, 'myregion', client)
        client.get_all_security_groups.return_value = [
            FakeSecurityGroup('sg_id1', ['i_id1', 'i_id2'])]
        client.delete_security_group.return_value = True
        uncleaned_resources = aws.ensure_cleanup(resource_details)
        client.delete_security_group.assert_called_once_with(name='sg_id1')
        self.assertEqual(client.get_all_instances.call_args_list,
                         [call(instance_ids=['i_id1', 'i_id2'])])
        self.assertEqual(uncleaned_resources, [])
        self.assertEqual(
            aws.client.terminate_instances.call_args_list,
            [call(instance_ids=['i_id1']), call(instance_ids=['i_id2'])])

    def test_ensure_cleanup_with_uncleaned_instances(self):
        client = MagicMock()
        resource_details = dict()
        resource_details['instances'] = ["i_id1", "i_id2"]
        aws = AWSAccount(None, 'myregion', client)
        err_msg = 'Instance error'
        client.terminate_instances.side_effect = [
            Exception(err_msg), Exception(err_msg)]
        client.get_all_security_groups.return_value = [
            FakeSecurityGroup('sg_id1', ['i_id1', 'i_id2'])]
        client.delete_security_group.return_value = True
        uncleaned_resources = aws.ensure_cleanup(resource_details)
        self.assertEqual(client.get_all_instances.call_args_list,
                         [call(instance_ids=['i_id1', 'i_id2'])])
        self.assertEqual(uncleaned_resources, [
            {'errors': [('i_id1', "Exception('Instance error',)"),
                        ('i_id2', "Exception('Instance error',)")],
             'resource': 'instances'}])

    def test_ensure_cleanup_with_uncleaned_sg(self):
        client = MagicMock()
        resource_details = dict()
        resource_details['instances'] = ["i_id1", "i_id2"]
        aws = AWSAccount(None, 'myregion', client)
        client.terminate_instances.side_effect = ["i_id1", "i_id2"]
        client.get_all_security_groups.return_value = [
            FakeSecurityGroup('sg_id1', [])]
        client.delete_security_group.return_value = False
        uncleaned_resources = aws.ensure_cleanup(resource_details)
        self.assertEqual(uncleaned_resources, [
            {'errors': [('sg_id1', 'Failed to delete')],
             'resource': 'security groups'}])
        self.assertEqual(client.get_all_instances.call_args_list,
                         [call(instance_ids=['i_id1', 'i_id2'])])

    def test_ensure_cleanup_with_uncleaned_instances_and_sg(self):
        client = MagicMock()
        resource_details = dict()
        resource_details['instances'] = ["i_id1", "i_id2"]
        aws = AWSAccount(None, 'myregion', client)
        ati_err_msg = 'Instance not found'
        client.terminate_instances.side_effect = [
             Exception(ati_err_msg), Exception(ati_err_msg)]
        client.get_all_security_groups.return_value = [
            FakeSecurityGroup('sg_id1', ['i_id1', 'i_id2'])]
        client.delete_security_group.side_effect = EC2ResponseError(
            400, "Bad Request",
            body={
                "RequestID": "xxx-yyy-zz",
                "Error": {
                    "Code": "Security group failed to delete",
                    "Message": "failed"
                }
            })
        uncleaned_resources = aws.ensure_cleanup(resource_details)
        self.assertEqual(client.get_all_instances.call_args_list,
                         [call(instance_ids=['i_id1', 'i_id2'])])
        self.assertEqual(
            uncleaned_resources,
            [{'errors': [
                ('i_id1', "Exception('Instance not found',)"),
                ('i_id2', "Exception('Instance not found',)")],
                'resource': 'instances'},
                {'errors': [
                    ('sg_id1',
                     "EC2ResponseError: 400 Bad Request\n{"
                     "'RequestID': 'xxx-yyy-zz', 'Error': {"
                     "'Message': 'failed', "
                     "'Code': 'Security group failed to delete'}}")],
                    'resource': 'security groups'}])


class TestAWSCleanUpSecurityGroups(TestCase):
    def test_delete_secgroup_not_in_use(self):
        secgroup = [("sg-foo", ["foo", "bar"])]
        instances = ["foo", "bar"]
        client = MagicMock()
        aws = AWSAccount(None, 'myregion', client)
        failures = aws.cleanup_security_groups(instances, secgroup)
        self.assertEqual(failures, [])
        self.assertEqual(
            client.delete_security_group.call_args, call(name='sg-foo'))

    def test_dont_delete_secgroup_in_use(self):
        secgroup = [("sg-foo", ["foo", "bar", "baz"])]
        instances = ["foo", "bar"]
        client = MagicMock()
        aws = AWSAccount(None, 'myregion', client)
        failures = aws.cleanup_security_groups(instances, secgroup)
        self.assertEqual(client.delete_security_group.call_count, 0)
        self.assertEqual(failures, [])

    def test_return_failure_on_exception(self):
        secgroup = [("sg-foo", ["foo", "bar"]), ("sg-bar", ["foo", "bar"])]
        instances = ["foo", "bar"]
        client = MagicMock(spec=["delete_security_group"])
        client.delete_security_group.side_effect = EC2ResponseError(
            400, "Bad Request",
            body={
                "RequestID": "xxx-yyy-zz",
                "Error": {
                    "Code": "InvalidSecurityGroup.NotFound",
                    "Message": "failed"
                }
            })
        aws = AWSAccount(None, 'myregion', client)
        failures = aws.cleanup_security_groups(instances, secgroup)
        self.assertEqual(client.delete_security_group.call_args_list,
                         [call(name='sg-foo'), call(name='sg-bar')])
        self.assertListEqual(failures,
                             [('sg-foo',
                               "EC2ResponseError: 400 Bad Request\n{"
                               "'RequestID': 'xxx-yyy-zz', 'Error': {"
                               "'Message': 'failed',"
                               " 'Code': 'InvalidSecurityGroup.NotFound'}}"),
                              ('sg-bar', "EC2ResponseError: 400 Bad Request\n{"
                               "'RequestID': 'xxx-yyy-zz', 'Error': {"
                               "'Message': 'failed',"
                               " 'Code': 'InvalidSecurityGroup.NotFound'}}")])

    def test_return_mixed_response(self):
        secgroup = [("sg-foo", ["foo", "bar"]), ("sg-bar", ["fooX", "barX"])]
        instances = ["foo", "bar", "fooX", "barX"]
        client = MagicMock(spec=["delete_security_group"])
        client.delete_security_group.side_effect = [
            True, False]
        aws = AWSAccount(None, 'myregion', client)
        failures = aws.cleanup_security_groups(instances, secgroup)
        self.assertEqual(failures, [('sg-bar', 'Failed to delete')])
        self.assertEqual(client.delete_security_group.call_args_list,
                         [call(name='sg-foo'), call(name='sg-bar')])

    def test_instance_mapped_to_more_than_one_secgroup(self):
        # Delete security group only if it has all the mapped instances
        # specified in the instances list.
        secgroup = [("sg-foo", ["foo", "bar"]), ("sg-bar", ["foo", "baz"])]
        instances = ["foo", "bar"]
        client = MagicMock()
        aws = AWSAccount(None, 'myregion', client)
        failures = aws.cleanup_security_groups(instances, secgroup)
        self.assertEqual(failures, [])
        self.assertEqual(aws.client.delete_security_group.call_count, 1)
        self.assertEqual(
            client.delete_security_group.call_args, call(name='sg-foo'))


class TestContainsOnlyKnownInstances(TestCase):
    def test_return_true_when_all_ids_known(self):
        instances = ["foo", "bar", "qnx"]
        sg_list = ["foo", "bar", "qnx"]
        self.assertEqual(
            contains_only_known_instances(instances, sg_list), True)

    def test_return_true_known_ids_are_subset(self):
        instances = ["foo", "bar", "qnx", "foo1"]
        sg_list = ["foo", "bar", "qnx"]
        self.assertEqual(
            contains_only_known_instances(instances, sg_list), True)

    def test_return_false_when_some_ids_unknown(self):
        instances = ["foo", "qnx"]
        sg_list = ["foo", "bar"]
        self.assertEqual(
            contains_only_known_instances(instances, sg_list),
            False)


class TestAttemptTerminateInstances(TestCase):
    def test_return_error_on_exception(self):
        client = MagicMock()
        instances = ["foo", "bar"]
        err_msg = "Instance not found"
        aws = AWSAccount(None, 'myregion', client)
        client.terminate_instances.side_effect = Exception(err_msg)
        failed = attempt_terminate_instances(aws, instances)
        self.assertEqual(failed,
                         [('foo', "Exception('{}',)".format(err_msg)),
                          ('bar', "Exception('{}',)".format(err_msg))])

    def test_return_with_no_error(self):
        client = MagicMock()
        instances = ["foo", "bar"]
        aws = AWSAccount(None, 'myregion', client)
        client.terminate_instances.return_value = ["foo", "bar"]
        failed = attempt_terminate_instances(aws, instances)
        self.assertEqual(client.terminate_instances.call_args_list,
                         [call(instance_ids=['foo']),
                          call(instance_ids=['bar'])])
        self.assertEqual(failed, [])

    def test_returns_has_some_error(self):
        client = MagicMock()
        instances = ["foo", "bar"]
        err_msg = "Instance not found"
        aws = AWSAccount(None, 'myregion', client)
        client.terminate_instances.side_effect = ["foo", Exception(err_msg)]
        failed = attempt_terminate_instances(aws, instances)
        self.assertEqual(client.terminate_instances.call_args_list, [
            call(instance_ids=['foo']), call(instance_ids=['bar'])])
        self.assertEqual(failed, [
            ('bar', "Exception('Instance not found',)")])


class TestGetSecurityGroups(TestCase):
    def test_instance_managed_by_single_security_group(self):
        client = MagicMock()
        instance_sec_groups = (('i_id1', 'sg_id1'), ('i_id2', 'sg_id1'))
        all_sec_groups = [FakeSecurityGroup('sg_id1', ['i_id1', 'i_id2'])]
        aws = AWSAccount(None, 'myregion', client)
        client.get_all_security_groups.return_value = all_sec_groups
        with patch.object(
                aws, 'iter_instance_security_groups',
                autospec=True, return_value=instance_sec_groups):
            sec_groups = aws.get_security_groups(['i_id1', 'i_id2'])
            self.assertEqual(sec_groups, [('sg_id1', ['i_id1', 'i_id2'])])

    def test_instance_managed_by_multiple_security_group(self):
        client = MagicMock()
        instance_sec_groups = (('i_id1', 'sg_id1'), ('i_id2', 'sg_id1'))
        all_sec_groups = [FakeSecurityGroup(
            'sg_id1', ['i_id1', 'i_id2']),
            FakeSecurityGroup('sg_id2', ['i_id1'])]
        aws = AWSAccount(None, 'myregion', client)
        client.get_all_security_groups.return_value = all_sec_groups
        with patch.object(
                aws, 'iter_instance_security_groups',
                autospec=True, return_value=instance_sec_groups):
            sec_groups = aws.get_security_groups(['i_id1', 'i_id2'])
            self.assertEqual(sec_groups,
                             [('sg_id1', ['i_id1', 'i_id2']),
                              ('sg_id2', ['i_id1'])])
