from contextlib import contextmanager
from datetime import datetime
import json
import os
from StringIO import StringIO
from unittest import TestCase

from mock import (
    Mock,
    patch,
    )

from make_image_streams import (
    is_china,
    iter_centos_images,
    iter_region_connection,
    get_parameters,
    make_aws_credentials,
    make_aws_items,
    make_item,
    make_item_name,
    write_item_streams,
    )
from utils import temp_dir


class TestIsChina(TestCase):

    def test_is_china(self):
        region = Mock()
        region.endpoint = 'foo.amazonaws.com.cn'
        self.assertIs(True, is_china(region))
        region.endpoint = 'foo.amazonaws.com'
        self.assertIs(False, is_china(region))


def make_mock_region(stem, name=None, endpoint=None):
    if endpoint is None:
        endpoint = '{}-end'.format(stem)
    region = Mock(endpoint=endpoint)
    if name is None:
        name = '{}-name'.format(stem)
    region.name = name
    return region


class IterRegionConnection(TestCase):

    def test_iter_region_connection(self):
        east = make_mock_region('east')
        west = make_mock_region('west')
        aws = {}
        with patch('make_image_streams.ec2.regions', autospec=True,
                   return_value=[east, west]) as regions_mock:
            connections = [x for x in iter_region_connection(aws, None)]
        regions_mock.assert_called_once_with()
        self.assertEqual(
            [east.connect.return_value, west.connect.return_value],
            connections)
        east.connect.assert_called_once_with(**aws)
        west.connect.assert_called_once_with(**aws)

    def test_gov_region(self):
        east = make_mock_region('east')
        gov = make_mock_region('west', name='foo-us-gov-bar')
        aws = {}
        with patch('make_image_streams.ec2.regions', autospec=True,
                   return_value=[east, gov]) as regions_mock:
            connections = [x for x in iter_region_connection(aws, None)]
        regions_mock.assert_called_once_with()
        self.assertEqual(
            [east.connect.return_value], connections)
        east.connect.assert_called_once_with(**aws)
        self.assertEqual(0, gov.connect.call_count)

    def test_china_region(self):
        east = make_mock_region('east')
        west = make_mock_region('west', endpoint='west-end.amazonaws.com.cn')
        east.name = 'east-name'
        west.name = 'west-name'
        aws = {'name': 'aws'}
        aws_cn = {'name': 'aws-cn'}
        with patch('make_image_streams.ec2.regions', autospec=True,
                   return_value=[east, west]) as regions_mock:
            connections = [x for x in iter_region_connection(aws, aws_cn)]
        regions_mock.assert_called_once_with(**aws)
        self.assertEqual(
            [east.connect.return_value, west.connect.return_value],
            connections)
        east.connect.assert_called_once_with(**aws)
        west.connect.assert_called_once_with(**aws_cn)

    def test_unauth_region(self):
        eu_central_1 = make_mock_region(
            'eu-central-1', endpoint='ec2.eu-central-1.amazonaws.com')
        ap_northeast_2 = make_mock_region(
            'ap-northeast-2', endpoint='ec2.ap-northeast-2.amazonaws.com')
        aws = {}
        with patch('make_image_streams.ec2.regions', autospec=True,
                   return_value=[eu_central_1, ap_northeast_2]
                   ) as regions_mock:
            connections = [x for x in iter_region_connection(aws, None)]
        regions_mock.assert_called_once_with()
        self.assertEqual([], connections)
        self.assertEqual(0, eu_central_1.connect.call_count)
        self.assertEqual(0, ap_northeast_2.connect.call_count)


@contextmanager
def mocked_iter_region(image_groups):
    connections = []
    for image_group in image_groups:
        conn = Mock()
        conn.get_all_images.return_value = image_group
        connections.append(conn)
    with patch('make_image_streams.iter_region_connection',
               return_value=connections,
               autospec=True) as irc_mock:
        yield irc_mock
    for conn in connections:
        conn.get_all_images.assert_called_once_with(filters={
            'owner_alias': 'aws-marketplace',
            'product_code': 'aw0evgkw8e5c1q413zgy5pjce',
            })


class IterCentosImages(TestCase):

    def test_iter_centos_images(self):
        aws = {'name': 'aws'}
        aws_cn = {'name': 'aws-cn'}
        east_imgs = ['east-1', 'east-2']
        west_imgs = ['west-1', 'west-2']
        with mocked_iter_region([east_imgs, west_imgs]) as irc_mock:
            imgs = list(iter_centos_images(aws, aws_cn))
        self.assertEqual(east_imgs + west_imgs, imgs)
        irc_mock.assert_called_once_with(aws, aws_cn)


class TestMakeAWSCredentials(TestCase):

    def test_happy_path(self):
        aws_credentials = make_aws_credentials({'credentials': {
            'access-key': 'foo',
            'secret-key': 'bar',
            }})
        self.assertEqual({
            'aws_access_key_id': 'foo',
            'aws_secret_access_key': 'bar',
            }, aws_credentials)

    def test_no_credentials(self):
        with self.assertRaisesRegexp(LookupError, 'No credentials found!'):
            make_aws_credentials({})

    def test_multiple_credentials(self):
        # If multiple credentials are present, an arbitrary credential will be
        # used.
        aws_credentials = make_aws_credentials({
            'credentials-1': {
                'access-key': 'foo',
                'secret-key': 'bar',
                },
            'credentials-2': {
                'access-key': 'baz',
                'secret-key': 'qux',
                },
            })
        self.assertIn(aws_credentials, [
            {'aws_access_key_id': 'foo', 'aws_secret_access_key': 'bar'},
            {'aws_access_key_id': 'baz', 'aws_secret_access_key': 'qux'},
            ])


def make_mock_image(region_name='us-northeast-3'):
    image = Mock(virtualization_type='hvm', id='qux',
                 root_device_type='ebs', architecture='x86_64')
    image.name = 'CentOS Linux 7 foo'
    image.region.endpoint = 'foo'
    image.region.name = region_name
    return image


class TestMakeItem(TestCase):

    def test_happy_path(self):
        image = make_mock_image()
        now = datetime(2001, 2, 3)
        item = make_item(image, now)
        self.assertEqual(item.content_id, 'com.ubuntu.cloud.released:aws')
        self.assertEqual(item.product_name,
                         'com.ubuntu.cloud:server:centos7:amd64')
        self.assertEqual(item.item_name, 'usne3he')
        self.assertEqual(item.version_name, '20010203')
        self.assertEqual(item.data, {
            'endpoint': 'https://foo',
            'region': 'us-northeast-3',
            'arch': 'amd64',
            'os': 'centos',
            'virt': 'hvm',
            'id': 'qux',
            'version': 'centos7',
            'label': 'release',
            'release': 'centos7',
            'release_codename': 'centos7',
            'release_title': 'Centos 7',
            'root_store': 'ebs',
            })

    def test_china(self):
        image = make_mock_image()
        image.region.endpoint = 'foo.amazonaws.com.cn'
        now = datetime(2001, 2, 3)
        item = make_item(image, now)
        self.assertEqual(item.content_id, 'com.ubuntu.cloud.released:aws-cn')
        self.assertEqual(item.data['endpoint'], 'https://foo.amazonaws.com.cn')

    def test_not_x86_64(self):
        image = make_mock_image()
        image.architecture = 'ppc128'
        now = datetime(2001, 2, 3)
        with self.assertRaisesRegexp(ValueError,
                                     'Architecture is "ppc128", not'
                                     ' "x86_64".'):
            make_item(image, now)

    def test_not_centos_7(self):
        image = make_mock_image()
        image.name = 'CentOS Linux 8'
        now = datetime(2001, 2, 3)
        with self.assertRaisesRegexp(ValueError,
                                     'Name "CentOS Linux 8" does not begin'
                                     ' with "CentOS Linux 7".'):
            make_item(image, now)


class TestGetParameters(TestCase):

    def test_happy_path(self):
        with patch.dict(os.environ, {'JUJU_DATA': 'foo'}):
            streams, creds_filename, aws, azure = get_parameters(['all',
                                                                  'bar'])
        self.assertEqual(creds_filename, 'foo/credentials.yaml')
        self.assertEqual(streams, 'bar')
        self.assertTrue(aws)
        self.assertTrue(azure)

    def test_azure(self):
        with patch.dict(os.environ, {'JUJU_DATA': 'foo'}):
            streams, creds_filename, aws, azure = get_parameters(['azure',
                                                                  'bar'])
        self.assertEqual(creds_filename, 'foo/credentials.yaml')
        self.assertEqual(streams, 'bar')
        self.assertFalse(aws)
        self.assertTrue(azure)

    def test_aws(self):
        with patch.dict(os.environ, {'JUJU_DATA': 'foo'}):
            streams, creds_filename, aws, azure = get_parameters(['aws',
                                                                  'bar'])
        self.assertEqual(creds_filename, 'foo/credentials.yaml')
        self.assertEqual(streams, 'bar')
        self.assertTrue(aws)
        self.assertFalse(azure)

    def test_no_juju_data(self):
        stderr = StringIO()
        with self.assertRaises(SystemExit):
            with patch('sys.stderr', stderr):
                get_parameters(['all', 'bar'])
        self.assertEqual(
            stderr.getvalue(),
            'JUJU_DATA must be set to a directory containing'
            ' credentials.yaml.\n')


class TestMakeItemName(TestCase):

    def test_make_item_name(self):
        item_name = make_item_name('us-east-1', 'paravirtual', 'instance')
        self.assertEqual(item_name, 'usee1pi')
        item_name = make_item_name('cn-northwest-3', 'hvm', 'ebs')
        self.assertEqual(item_name, 'cnnw3he')


def load_json(parent, filename):
    with open(os.path.join(parent, 'streams', 'v1', filename)) as f:
        return json.load(f)


class TestMakeAwsItems(TestCase):

    def test_happy_path(self):
        now = datetime(2001, 2, 3)
        east_image = make_mock_image(region_name='us-east-1')
        west_image = make_mock_image(region_name='us-west-1')
        all_credentials = {
            'aws': {'credentials': {
                'access-key': 'foo',
                'secret-key': 'bar',
                }},
            'aws-china': {'credentials': {
                'access-key': 'baz',
                'secret-key': 'qux',
                }},
            }
        now = datetime(2001, 2, 3)
        credentials = make_aws_credentials(all_credentials['aws'])
        china_credentials = make_aws_credentials(all_credentials['aws-china'])
        with mocked_iter_region([[east_image], [west_image]]) as irc_mock:
            items = make_aws_items(all_credentials, now)
        irc_mock.assert_called_once_with(credentials, china_credentials)
        self.assertEqual([make_item(east_image, now),
                          make_item(west_image, now)], items)


class TestWriteItemStreams(TestCase):

    def test_write_item_streams(self):
        now = datetime(2001, 2, 3)
        east_image = make_mock_image(region_name='us-east-1')
        west_image = make_mock_image(region_name='us-west-1')
        items = [make_item(west_image, now), make_item(east_image, now)]
        with temp_dir() as streams:
            with patch('simplestreams.util.timestamp',
                       return_value='now'):
                with patch('sys.stderr'):
                    write_item_streams(items, streams)
            self.assertFalse(
                os.path.exists(os.path.join(streams, 'streams', 'v1',
                                            'index2.json')))
            index = load_json(streams, 'index.json')
            releases = load_json(streams, 'com.ubuntu.cloud.released-aws.json')
        self.assertEqual(
            {'format': 'index:1.0', 'updated': 'now', 'index': {
                'com.ubuntu.cloud.released:aws': {
                    'format': 'products:1.0',
                    'updated': 'now',
                    'datatype': 'image-ids',
                    'path': 'streams/v1/com.ubuntu.cloud.released-aws.json',
                    'products': ['com.ubuntu.cloud:server:centos7:amd64'],
                    }
                }}, index)
        expected = {
            'content_id': 'com.ubuntu.cloud.released:aws',
            'format': 'products:1.0',
            'updated': 'now',
            'datatype': 'image-ids',
            'products': {'com.ubuntu.cloud:server:centos7:amd64': {
                'endpoint': 'https://foo',
                'arch': 'amd64',
                'release_title': 'Centos 7',
                'label': 'release',
                'release_codename': 'centos7',
                'version': 'centos7',
                'release': 'centos7',
                'os': 'centos',
                'versions': {'20010203': {
                    'items': {
                        'usww1he': {
                            'id': 'qux',
                            'region': 'us-west-1',
                            'root_store': 'ebs',
                            'virt': 'hvm',
                            },
                        'usee1he': {
                            'id': 'qux',
                            'region': 'us-east-1',
                            'root_store': 'ebs',
                            'virt': 'hvm',
                            },
                        }
                    }},
                }},
            }
        self.assertEqual(releases, expected)
