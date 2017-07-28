from collections import namedtuple
from datetime import (
    datetime,
    timedelta,
)
from mock import (
    Mock,
    patch,
)

import pytz

from tests import TestCase
from winazurearm import (
    ARMClient,
    DEFAULT_RESOURCE_PREFIX,
    delete_instance,
    delete_resources,
    find_vm_instance,
    list_resources,
    main,
    OLD_MACHINE_AGE,
    ResourceGroupDetails,
)


AZURE_ENVIRON = {
    'AZURE_SUBSCRIPTION_ID': 'subscription_id',
    'AZURE_CLIENT_ID': 'client_id',
    'AZURE_SECRET': 'secret',
    'AZURE_TENANT': 'tenant',
}

# The azure unit test use namedtuples like these to avoid tight
# coupling between services. When Azure ARM is stable, we might want
# to use the real objects.
ResourceGroup = namedtuple('ResourceGroup', ['name'])
StorageAccount = namedtuple('StorageAccount', ['name', 'creation_time'])
VirtualMachine = namedtuple('VirtualMachine', ['name', 'vm_id'])
Network = namedtuple('Network', ['name'])
Address = namedtuple('Address', ['name', 'ip_address'])


class FakePoller:

    def __init__(self, result_data=None):
        self.is_done = False
        self.result_data = result_data

    def done(self):
        return self.is_done

    def result(self):
        if self.is_done:
            raise Exception('It is an error to call result after done.')
        self.is_done = True
        return self.result_data


def fake_init_services(client):
    """Repurpose the lazy init to install mocks."""
    # client.resource.resource_groups.list()
    client.resource = Mock(resource_groups=Mock(
        list=Mock(return_value=[]),
        delete=Mock(return_value=None)))
    # client.storage.storage_accounts.list_by_resource_group()
    client.storage = Mock(
        storage_accounts=Mock(list_by_resource_group=Mock(return_value=[])))
    # client.compute.virtual_machines.list()
    client.compute = Mock(virtual_machines=Mock(
        list=Mock(return_value=[]),
        delete=Mock(return_value=None)))
    # client.network.public_ip_addresses.list()
    # client.network.virtual_networks.list()
    client.network = Mock(
        public_ip_addresses=Mock(list=Mock(return_value=[])),
        virtual_networks=Mock(list=Mock(return_value=[])))


@patch('winazurearm.ARMClient.init_services',
       autospec=True, side_effect=fake_init_services)
class WinAzureARMTestCase(TestCase):

    test_environ = AZURE_ENVIRON

    def test_main_list_resources(self, is_mock):
        client = ARMClient('subscription_id', 'client_id', 'secret', 'tenant')
        with patch('winazurearm.list_resources', autospec=True) as lr_mock:
            code = main(['winazurearm.py', 'list-resources', 'juju-deploy*'])
        self.assertEqual(0, code)
        self.assertEqual(1, is_mock.call_count)
        lr_mock.assert_called_once_with(
            client, glob='juju-deploy*', print_out=True, recursive=False)

    def test_main_delete_resources(self, is_mock):
        client = ARMClient('subscription_id', 'client_id', 'secret', 'tenant')
        with patch('winazurearm.delete_resources', autospec=True) as dr_mock:
            code = main(['winazurearm.py', 'delete-resources', 'juju-deploy*'])
        self.assertEqual(0, code)
        self.assertEqual(1, is_mock.call_count)
        dr_mock.assert_called_once_with(
            client, glob='juju-deploy*', old_age=OLD_MACHINE_AGE)

    def test_main_delete_resources_old_age(self, is_mock):
        client = ARMClient('subscription_id', 'client_id', 'secret', 'tenant')
        with patch('winazurearm.delete_resources', autospec=True) as dr_mock:
            code = main(['winazurearm.py', 'delete-resources',
                         '-o', '2', 'juju-deploy*'])
        self.assertEqual(0, code)
        self.assertEqual(1, is_mock.call_count)
        dr_mock.assert_called_once_with(
            client, glob='juju-deploy*', old_age=2)

    def test_main_delete_instance_instance_id(self, is_mock):
        client = ARMClient('subscription_id', 'client_id', 'secret', 'tenant')
        with patch('winazurearm.delete_instance', autospec=True) as di_mock:
            code = main(['winazurearm.py', 'delete-instance', 'instance-id'])
        self.assertEqual(0, code)
        self.assertEqual(1, is_mock.call_count)
        di_mock.assert_called_once_with(
            client, 'instance-id', resource_group=None)

    def test_main_delete_instance_not_found(self, is_mock):
        client = ARMClient('subscription_id', 'client_id', 'secret', 'tenant')
        with patch('winazurearm.delete_instance', autospec=True,
                   side_effect=ValueError) as di_mock:
            code = main(['winazurearm.py', 'delete-instance', 'instance-id'])
        self.assertEqual(1, code)
        self.assertEqual(1, is_mock.call_count)
        di_mock.assert_called_once_with(
            client, 'instance-id', resource_group=None)

    def test_main_delete_instance_name_group(self, is_mock):
        client = ARMClient('subscription_id', 'client_id', 'secret', 'tenant')
        with patch('winazurearm.delete_instance', autospec=True) as di_mock:
            code = main(['winazurearm.py', 'delete-instance', 'name', 'group'])
        self.assertEqual(0, code)
        self.assertEqual(1, is_mock.call_count)
        di_mock.assert_called_once_with(client, 'name', resource_group='group')

    def test_list_resources(self, is_mock):
        client = ARMClient('subscription_id', 'client_id', 'secret', 'tenant')
        client.init_services()
        groups = [ResourceGroup('juju-foo-0'), ResourceGroup('juju-bar-1')]
        client.resource.resource_groups.list.return_value = groups
        result = list_resources(client, 'juju-bar*')
        rgd = ResourceGroupDetails(client, groups[-1])
        self.assertEqual([rgd], result)
        client.resource.resource_groups.list.assert_called_once_with()

    def test_list_resources_ignore_default(self, is_mock):
        # Default resources are created by Azure. They should only be
        # seen via the UI. A glob for everything will still ignore defaults.
        client = ARMClient('subscription_id', 'client_id', 'secret', 'tenant')
        client.init_services()
        groups = [ResourceGroup('{}-network'.format(DEFAULT_RESOURCE_PREFIX))]
        client.resource.resource_groups.list.return_value = groups
        result = list_resources(client, '*')
        self.assertEqual([], result)

    def test_list_resources_recursive(self, is_mock):
        client = ARMClient('subscription_id', 'client_id', 'secret', 'tenant')
        client.init_services()
        # For the call to find many groups.
        a_group = ResourceGroup('juju-bar-1')
        b_group = ResourceGroup('juju-foo-0')
        client.resource.resource_groups.list.return_value = [a_group, b_group]
        # For the call to load a ResourceGroupDetails instance.
        storage_account = StorageAccount('abcd-12', datetime.now(tz=pytz.UTC))
        client.storage.storage_accounts.list_by_resource_group.return_value = [
            storage_account]
        virtual_machine = VirtualMachine('admin-machine-0', 'bcde-1234')
        client.compute.virtual_machines.list.return_value = [virtual_machine]
        address = Address('machine-0-public-ip', '1.2.3.4')
        client.network.public_ip_addresses.list.return_value = [address]
        network = Network('juju-bar-network-1')
        client.network.virtual_networks.list.return_value = [network]
        # The addition of recursive=True will get the details of the
        # subordinate resources and set is_loaded to True.
        result = list_resources(client, 'juju-bar*', recursive=True)
        rgd = ResourceGroupDetails(
            client, a_group, storage_accounts=[storage_account],
            vms=[virtual_machine], addresses=[address], networks=[network])
        rgd.is_loaded = True
        self.assertEqual([rgd], result)

    def test_delete_resources_found_old(self, is_mock):
        now = datetime.now(tz=pytz.utc)
        client = ARMClient('subscription_id', 'client_id', 'secret', 'tenant')
        client.init_services()
        group = ResourceGroup('juju-bar-1')
        client.resource.resource_groups.list.return_value = [group]
        # The resource_groups's storage_account is 4 hours old.
        storage_account = StorageAccount('abcd-12', now - timedelta(hours=4))
        client.storage.storage_accounts.list_by_resource_group.return_value = [
            storage_account]
        poller = FakePoller()
        client.resource.resource_groups.delete.return_value = poller
        # Delete resource groups that are 2 hours old.
        count = delete_resources(client, 'juju-bar*', old_age=2, now=now)
        self.assertEqual(1, count)
        client.resource.resource_groups.delete.assert_called_once_with(
            'juju-bar-1')
        self.assertIs(True, poller.is_done)

    def test_delete_resources_not_found_old(self, is_mock):
        now = datetime.now(tz=pytz.utc)
        client = ARMClient('subscription_id', 'client_id', 'secret', 'tenant')
        client.init_services()
        group = ResourceGroup('juju-bar-1')
        client.resource.resource_groups.list.return_value = [group]
        # The resource_groups's storage_account is 2 hours old.
        storage_account = StorageAccount('abcd-12', now - timedelta(hours=2))
        client.storage.storage_accounts.list_by_resource_group.return_value = [
            storage_account]
        # Delete resource groups that are 8 hours old.
        count = delete_resources(client, 'juju-bar*', old_age=8, now=now)
        self.assertEqual(0, count)
        self.assertEqual(0, client.resource.resource_groups.delete.call_count)

    def test_delete_resources_read_only(self, is_mock):
        now = datetime.now(tz=pytz.utc)
        client = ARMClient(
            'subscription_id', 'client_id', 'secret', 'tenant', read_only=True)
        client.init_services()
        group = ResourceGroup('juju-bar-1')
        client.resource.resource_groups.list.return_value = [group]
        # The resource_groups's storage_account is 4 hours old.
        storage_account = StorageAccount('abcd-12', now - timedelta(hours=4))
        client.storage.storage_accounts.list_by_resource_group.return_value = [
            storage_account]
        count = delete_resources(client, 'juju-bar*', old_age=2, now=now)
        self.assertEqual(0, count)
        self.assertEqual(0, client.resource.resource_groups.delete.call_count)

    def test_delete_resources_poller_already_done(self, is_mock):
        now = datetime.now(tz=pytz.utc)
        client = ARMClient('subscription_id', 'client_id', 'secret', 'tenant')
        client.init_services()
        group = ResourceGroup('juju-bar-1')
        client.resource.resource_groups.list.return_value = [group]
        # The resource_groups's storage_account is 4 hours old.
        storage_account = StorageAccount('abcd-12', now - timedelta(hours=4))
        client.storage.storage_accounts.list_by_resource_group.return_value = [
            storage_account]
        poller = FakePoller()
        poller.is_done = True
        client.resource.resource_groups.delete.return_value = poller
        count = delete_resources(client, 'juju-bar*', old_age=2, now=now)
        self.assertEqual(1, count)
        self.assertEqual(1, client.resource.resource_groups.delete.call_count)

    def test_delete_resources_poller_is_none(self, is_mock):
        now = datetime.now(tz=pytz.utc)
        client = ARMClient('subscription_id', 'client_id', 'secret', 'tenant')
        client.init_services()
        group = ResourceGroup('juju-bar-1')
        client.resource.resource_groups.list.return_value = [group]
        # The resource_groups's storage_account is 4 hours old.
        storage_account = StorageAccount('abcd-12', now - timedelta(hours=4))
        client.storage.storage_accounts.list_by_resource_group.return_value = [
            storage_account]
        count = delete_resources(client, 'juju-bar*', old_age=2, now=now)
        self.assertEqual(1, count)
        self.assertEqual(1, client.resource.resource_groups.delete.call_count)

    def test_delete_resources_old_age_0(self, is_mock):
        now = datetime.now(tz=pytz.utc)
        client = ARMClient('subscription_id', 'client_id', 'secret', 'tenant')
        client.init_services()
        a_group = ResourceGroup('juju-bar-1')
        b_group = ResourceGroup('juju-foo-0')
        client.resource.resource_groups.list.return_value = [a_group, b_group]
        poller = FakePoller()
        client.resource.resource_groups.delete.return_value = poller
        # Delete resource groups that are 0 hours old.
        # All matched resource_groups are deleted
        count = delete_resources(client, 'juju-bar*', old_age=0, now=now)
        self.assertEqual(1, count)
        self.assertEqual(1, client.resource.resource_groups.delete.call_count)
        self.assertIs(True, poller.is_done)

    # https://bugs.launchpad.net/juju-ci-tools/+bug/1613767
    def xxx_test_delete_resources_only_network(self, is_mock):
        now = datetime.now(tz=pytz.utc)
        client = ARMClient('subscription_id', 'client_id', 'secret', 'tenant')
        client.init_services()
        group = ResourceGroup('juju-bar-1')
        client.resource.resource_groups.list.return_value = [group]
        # The resource_group has a network, but nothing else
        network = Network('juju-bar-network-1')
        client.network.virtual_networks.list.return_value = [network]
        poller = FakePoller()
        client.resource.resource_groups.delete.return_value = poller
        count = delete_resources(client, 'juju-bar*', old_age=2, now=now)
        self.assertEqual(1, count)
        self.assertEqual(1, client.resource.resource_groups.delete.call_count)

    def test_find_vm_instance(self, is_mock):
        client = ARMClient('subscription_id', 'client_id', 'secret', 'tenant')
        client.init_services()
        rgd1 = ResourceGroupDetails(
            client, ResourceGroup('one'),
            vms=[VirtualMachine('name-0', 'id-a'),
                 VirtualMachine('name-1', 'id-b')])
        rgd2 = ResourceGroupDetails(
            client, ResourceGroup('two'),
            vms=[VirtualMachine('name-0', 'id-y'),
                 VirtualMachine('name-1', 'id-z')])
        resources = [rgd1, rgd2]
        self.assertEqual(
            (None, None), find_vm_instance(resources, 'id-q', None))
        self.assertEqual(
            (rgd2, rgd2.vms[0]), find_vm_instance(resources, 'id-y', None))
        self.assertEqual(
            (rgd2, rgd2.vms[0]), find_vm_instance(resources, 'name-0', 'two'))
        self.assertEqual(
            (None, None), find_vm_instance(resources, 'name-0', 'three'))
        self.assertEqual(
            (None, None), find_vm_instance(resources, 'name-9', 'two'))

    def test_delete_instance_with_name_and_resource_group(self, is_mock):
        client = ARMClient('subscription_id', 'client_id', 'secret', 'tenant')
        client.init_services()
        poller = FakePoller()
        client.compute.virtual_machines.delete.return_value = poller
        vm1 = VirtualMachine('name-0', 'id-a')
        rgd1 = ResourceGroupDetails(client, ResourceGroup('one'), vms=[vm1])
        with patch('winazurearm.list_resources', autospec=True,
                   return_value=[rgd1]) as lr_mock:
            # Passing just a name and group will take the group glob path.
            delete_instance(client, 'name-0', 'one')
        lr_mock.assert_called_once_with(client, glob='one', recursive=True)
        client.compute.virtual_machines.delete.assert_called_once_with(
            'one', 'name-0')
        self.assertIs(True, poller.is_done)

    def test_delete_instance_with_id(self, is_mock):
        client = ARMClient('subscription_id', 'client_id', 'secret', 'tenant')
        client.init_services()
        poller = FakePoller()
        client.compute.virtual_machines.delete.return_value = poller
        vm1 = VirtualMachine('name-0', 'id-a')
        rgd1 = ResourceGroupDetails(client, ResourceGroup('one'), vms=[vm1])
        vm2 = VirtualMachine('name-0', 'id-b')
        rgd2 = ResourceGroupDetails(client, ResourceGroup('two'), vms=[vm2])
        with patch('winazurearm.list_resources', autospec=True,
                   return_value=[rgd1, rgd2]) as lr_mock:
            # Passing just an id will take the * glob path.
            delete_instance(client, 'id-a')
        lr_mock.assert_called_once_with(client, glob='*', recursive=True)
        client.compute.virtual_machines.delete.assert_called_once_with(
            'one', 'name-0')
        self.assertIs(True, poller.is_done)

    def test_delete_instance_without_match(self, is_mock):
        client = ARMClient('subscription_id', 'client_id', 'secret', 'tenant')
        client.init_services()
        vm1 = VirtualMachine('name-0', 'id-a')
        rgd1 = ResourceGroupDetails(client, ResourceGroup('one'), vms=[vm1])
        with patch('winazurearm.list_resources', autospec=True,
                   return_value=[rgd1]):
            # Passing an non-existent id bypasses the call to delete.
            with self.assertRaises(ValueError):
                delete_instance(client, 'id-z')
        self.assertEqual(0, client.compute.virtual_machines.delete.call_count)
