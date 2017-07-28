#!/usr/bin/env python
from argparse import ArgumentParser
import os
import re
import subprocess
from textwrap import dedent
from utility import s3_cmd
import yaml


def win_test(script_dir, address, juju_home, revision_build):
    host = 'Administrator@{}'.format(address)
    private_key = os.path.join(juju_home, 'staging-juju-rsa')
    revision_build_url = (
        's3://juju-qa-data/juju-ci/products/version-{}'.format(revision_build))
    win_client_url = '{}/build-win-client/'.format(revision_build_url)
    output = s3_cmd(['ls', '-r', win_client_url])
    urls = sorted(l.split()[3] for l in output.splitlines())
    installer = [u for u in urls if re.search('juju-setup-.*\.exe', u)][-1]
    s3_cmd(['sync', installer, '.'])
    install_file = installer.split('/')[-1]
    deploy_job = (
        'c:\\\\Users\\\\Administrator\\\\juju-ci-tools\\\\deploy_job.py')
    with open('run-file', 'w') as run_file:
        run_file.write(dedent("""
            ci/$1 /verysilent
            juju version
            juju destroy-environment --force -y win-client-deploy
            mkdir logs
            python {deploy_job} parallel-win-client \
                'c:\\Program Files (x86)\\Juju\\juju.exe' \
                logs win-client-deploy --series xenial --use-charmstore \
                --agent-stream revision-build-{revision_build}
            """.format(revision_build=revision_build, deploy_job=deploy_job)))

    ci = [install_file, 'run-file']
    with open('foo.yaml', 'w') as config:
        yaml.dump({
            'install': {'ci': ci},
            'command': ['ci/run-file', install_file],
            }, config)
    subprocess.check_call(['workspace-run', '-v', 'foo.yaml', host, '-i',
                           private_key])


def main():
    parser = ArgumentParser()
    parser.add_argument('address',
                        help='The IP or DNS address the windows test machine.')
    parser.add_argument('revision_build',
                        help='Revision-build to test.')
    parser.add_argument(
        '--juju-home', default=os.environ.get('JUJU_HOME'),
        help='The location of cloud-city and staging-juju-rsa.')
    script_dir = os.path.dirname(__file__)
    win_test(script_dir=script_dir, **parser.parse_args().__dict__)


if __name__ == '__main__':
    main()
