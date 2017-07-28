#!/usr/bin/python

from __future__ import print_function

from argparse import ArgumentParser
from datetime import (
    datetime,
    timedelta,
)
import re
import sys
from textwrap import wrap

from launchpadlib.launchpad import Launchpad


DEVEL = 'development'
PROPOSED = 'proposed'

DEVEL_TEMPLATE = """\
A new development release of Juju, {version}, is here!


## What's new?

{notable}


## How do I get it?

If you are running Ubuntu, you can get it from the juju devel ppa:

    sudo add-apt-repository ppa:juju/devel
    sudo apt-get update; sudo apt-get install juju-2.0

Or install it from the snap store

    snap install juju --beta --devmode

Windows, Centos, and MacOS users can get a corresponding installer at:

    https://launchpad.net/juju/+milestone/{version}


## Feedback Appreciated!

We encourage everyone to subscribe the mailing list at
juju@lists.ubuntu.com and join us on #juju on freenode. We would love to hear
your feedback and usage of juju.


## Anything else?

You can read more information about what's in this release by viewing the
release notes here:

https://jujucharms.com/docs/devel/temp-release-notes

"""

PROPOSED_TEMPLATE = """\
A new proposed stable release of Juju, {version}, is here!
This release may replace version {previous} on {release_date}.


## What's new?

{notable}


## How do I get it?

If you are running Ubuntu, you can get it from the juju proposed ppa:

    sudo add-apt-repository ppa:juju/proposed
    sudo apt-get update; sudo apt-get install juju-core

Windows, Centos, and MacOS users can get a corresponding installer at:

    https://launchpad.net/juju-core/+milestone/{version}

Proposed releases use the "proposed" simple-streams. You must configure
the `agent-stream` option in your environments.yaml to use the matching
juju agents.


## Feedback Appreciated!

We encourage everyone to subscribe the mailing list at
juju@lists.ubuntu.com and join us on #juju on freenode. We would love to hear
your feedback and usage of juju.


## Resolved issues

{resolved_text}

"""


def get_lp_bug_tasks(script, milestone_name):
    """Return an iterators of Lp BugTasks,"""
    lp = Launchpad.login_with(
        script, service_root='https://api.launchpad.net', version='devel')
    if milestone_name.startswith('1.'):
        project = lp.projects['juju-core']
    else:
        project = lp.projects['juju']
    milestone = project.getMilestone(name=milestone_name)
    return milestone.searchTasks(status=['Fix Committed'])


def get_purpose(milestone):
    """Return PROPOSED or DEVEL as implied by the milestone version."""
    parts = milestone.split('.')
    major = minor = micro = None
    if len(parts) == 2:
        major, minor = parts
    elif len(parts) == 3:
        major, minor, micro = parts
    else:
        raise ValueError(
            'Milestone version is not understood to be major.minor.micro.')
    if re.search('[a-z]+', minor):
        return DEVEL
    else:
        return PROPOSED


def get_bugs(script, milestone):
    """Return a list of bug tuples (id, title)."""
    bug_tasks = get_lp_bug_tasks(script, milestone)
    bugs = []
    for bugtask in bug_tasks:
        bug = bugtask.bug
        if 'tech-debt' not in bug.tags:
            bugs.append((bug.id, bug.title.capitalize()))
    return bugs


def make_resolved_text(bugs):
    """Return the list of bug tuples as formatted text."""
    resolved = []
    for bug in bugs:
        lines = wrap(
            '* {0}'.format(bug[1]), width=70, initial_indent='  ',
            subsequent_indent='    ')
        lines.append('    Lp {0}'.format(bug[0]))
        text = '\n'.join(lines)
        resolved.append(text)
    resolved_text = '\n\n'.join(resolved)
    return resolved_text


def make_release_date(now=None):
    if now is None:
        now = datetime.utcnow()
    week = timedelta(days=7)
    future = now + week
    release_date = future.strftime('%A %B %d')
    return release_date


def make_notes(version, purpose, resolved_text, previous=None, notable=None):
    """Return to formatted release notes."""
    if purpose == DEVEL:
        template = DEVEL_TEMPLATE
    else:
        template = PROPOSED_TEMPLATE
    if notable is None:
        notable = 'This releases addresses stability and performance issues.'
    elif notable == '':
        notable = '[[Add the notable changes here.]]'
    release_date = make_release_date()
    text = template.format(
        version=version, purpose=purpose, resolved_text=resolved_text,
        notable=notable, previous=previous, release_date=release_date)
    # Normalise the whitespace between sections. The text can have
    # extra whitespae when blank sections are interpolated.
    text = text.replace('\n\n\n\n', '\n\n\n')
    return text


def save_notes(text, file_name):
    """Save the notes to the named file or print to stdout."""
    if file_name is None:
        print(text)
    else:
        with open(file_name, 'w') as rn:
            rn.write(text)


def parse_args(args=None):
    parser = ArgumentParser('Create release notes from a milestone')
    parser.add_argument(
        '--previous', help='the previous release.', default=None)
    parser.add_argument(
        '--file-name', help='the name of file to write.', default=None)
    parser.add_argument('milestone', help='the milestone to examine.')
    return parser.parse_args(args)


def main(argv):
    args = parse_args(argv[1:])
    purpose = get_purpose(args.milestone)
    bugs = get_bugs(argv[0], args.milestone)
    resolved_text = make_resolved_text(bugs)
    text = make_notes(args.milestone, purpose, resolved_text, args.previous)
    save_notes(text, args.file_name)
    print('These are the bugs the package fixes:')
    print(' '.join([str(i) for i, t in bugs]))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
