# Copyright 2015 Canonical Ltd.
# Licensed under the AGPLv3, see LICENCE file for details.

#
# This file has been and should be formatted using pyfmt(1).
#

from __future__ import print_function

import argparse
import os
import re
import shutil
import subprocess
import sys
import time

# StringIO: accommodate Python2 & Python3

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

# These options are to be removed from a sub-interface and applied to
# the new bridged interface.

BRIDGE_ONLY_OPTIONS = {'address', 'gateway', 'netmask', 'dns-nameservers', 'dns-search', 'dns-sortlist'}


class SeekableIterator(object):
    """An iterator that supports relative seeking."""

    def __init__(self, iterable):
        self.iterable = iterable
        self.index = 0

    def __iter__(self):
        return self

    def next(self):  # Python 2
        try:
            value = self.iterable[self.index]
            self.index += 1
            return value
        except IndexError:
            raise StopIteration

    def __next__(self):  # Python 3
        return self.next()

    def seek(self, n, relative=False):
        if relative:
            self.index += n
        else:
            self.index = n
        if self.index < 0 or self.index >= len(self.iterable):
            raise IndexError


class PhysicalInterface(object):
    """Represents a physical ('auto') interface."""

    def __init__(self, definition):
        self.name = definition.split()[1]

    def __str__(self):
        return self.name


class LogicalInterface(object):
    """Represents a logical ('iface') interface."""

    def __init__(self, stanzas, has_auto_stanza):
        self.name = stanzas[0].name
        self.is_alias = ":" in self.name
        self.stanzas = stanzas
        self.has_auto_stanza = has_auto_stanza
        self.parent = None

        self.is_loopback = False
        self.is_bonded = False
        self.is_vlan = False
        self.is_bridge = False
        self.has_bond_master_option = False
        self.bond_master_options = False
        self.bridge_ports = []
        self._process_stanzas()

    def _process_stanzas(self):
        for s in self.stanzas:
            self._process_stanza(s)

    def _process_stanza(self, s):
        if s.method == 'loopback':
            self.is_loopback = True
            # Loopback cannot have options.
            return
        if not self.is_bonded:
            self.is_bonded = any((o.startswith("bond-") for o in s.options))
        is_bridge, bridge_ports = s.has_any_option(['bridge_ports'])
        if is_bridge:
            self.is_bridge = True
            self.bridge_ports.extend(bridge_ports)
        if not self.has_bond_master_option:
            self.has_bond_master_option, _ = s.has_any_option(['bond-master'])
        if not self.is_vlan:
            self.is_vlan = any((x.startswith("vlan-raw-device") for x in s.options))

    def __str__(self):
        return self.name

    def _bridge(self, prefix, bridge_name):
        if bridge_name is None:
            bridge_name = prefix + self.name
        # Note: the testing order here is significant.
        if self.is_loopback or self.is_bridge or self.has_bond_master_option:
            return self._bridge_unchanged()
        elif self.is_alias:
            # XXX(axw) should this be checking the same conditions as above?
            # i.e. self.parent and (self.parent.is_loopback or self.parent.is_bridge or self.parent.has_bond_master_option)
            if self.parent and self.parent.is_bridge:
                # if we didn't change the parent interface
                # then we don't change the aliases neither.
                return self._bridge_unchanged()
            else:
                return self._bridge_alias(bridge_name)
        elif self.is_vlan:
            return self._bridge_vlan(bridge_name)
        elif self.is_bonded:
            return self._bridge_bond(bridge_name)
        else:
            return self._bridge_device(bridge_name)

    def _bridge_device(self, bridge_name):
        stanzas = []
        if self.has_auto_stanza:
            stanzas.append(AutoStanza(self.name))
        for s in self.stanzas:
            stanzas.append(self._iface_stanza(s))
        stanzas.append(AutoStanza(bridge_name))
        for i, s in enumerate(self.stanzas):
            options = list(s.options)
            if i == 0:
                # Only add bridge_ports to one of the iface stanzas.
                options.append("bridge_ports {}".format(self.name))
            options = prune_options(options, ['mtu'])
            iface_stanza = IfaceStanza(bridge_name, s.family, s.method, options)
            stanzas.append(iface_stanza)
        return stanzas

    def _bridge_vlan(self, bridge_name):
        stanzas = []
        if self.has_auto_stanza:
            stanzas.append(AutoStanza(self.name))
        for s in self.stanzas:
            stanzas.append(self._iface_stanza(s))
        stanzas.append(AutoStanza(bridge_name))
        for i, s in enumerate(self.stanzas):
            options = list(s.options)
            if i == 0:
                # Only add bridge_ports to one of the iface stanzas.
                options.append("bridge_ports {}".format(self.name))
            options = prune_options(options, ['mtu', 'vlan_id', 'vlan-raw-device'])
            iface_stanza = IfaceStanza(bridge_name, s.family, s.method, options)
            stanzas.append(iface_stanza)
        return stanzas

    def _bridge_alias(self, bridge_name):
        stanzas = []
        if self.has_auto_stanza:
            stanzas.append(AutoStanza(bridge_name))
        for s in self.stanzas:
            iface_stanza = IfaceStanza(bridge_name, s.family, s.method, list(s.options))
            stanzas.append(iface_stanza)
        return stanzas

    def _bridge_bond(self, bridge_name):
        stanzas = []
        if self.has_auto_stanza:
            stanzas.append(AutoStanza(self.name))
        for s in self.stanzas:
            stanzas.append(self._iface_stanza(s))
        stanzas.append(AutoStanza(bridge_name))
        for i, s in enumerate(self.stanzas):
            options = [x for x in s.options if not x.startswith("bond")]
            options = prune_options(options, ['mtu'])
            if i == 0:
                # Only add bridge_ports to one of the iface stanzas.
                options.append("bridge_ports {}".format(self.name))
            iface_stanza = IfaceStanza(bridge_name, s.family, s.method, options)
            stanzas.append(iface_stanza)
        return stanzas

    def _bridge_unchanged(self):
        stanzas = []
        if self.has_auto_stanza:
            stanzas.append(AutoStanza(self.name))
        stanzas.extend(self.stanzas)
        return stanzas

    def _iface_stanza(self, stanza):
        options = prune_options(stanza.options, BRIDGE_ONLY_OPTIONS)
        return IfaceStanza(self.name, stanza.family, "manual", options)


class Stanza(object):
    """Represents one stanza together with all of its options."""

    def __init__(self, definition, options=None):
        if not options:
            options = []
        self.definition = definition
        self.options = options
        self.is_logical_interface = definition.startswith('iface ')
        self.is_physical_interface = definition.startswith('auto ')
        self.phy = None
        if self.is_logical_interface:
            _, self.name, self.family, self.method = definition.split()
        if self.is_physical_interface:
            self.phy = PhysicalInterface(definition)

    def __str__(self):
        return self.definition

    def has_any_option(self, options):
        for o in self.options:
            words = o.split()
            ident = words[0]
            if ident in options:
                return True, words[1:]
        return False, []


def prune_options(options, invalid_options):
    result = []
    for o in options:
        words = o.split()
        if words[0] not in invalid_options:
            result.append(o)
    return result



class NetworkInterfaceParser(object):
    """Parse a network interface file into a set of stanzas."""

    @classmethod
    def is_stanza(cls, s):
        return re.match(r'^(iface|mapping|auto|allow-|source)', s)

    def __init__(self, filename):
        self._stanzas = []
        with open(filename, 'r') as f:
            lines = f.readlines()
        line_iterator = SeekableIterator(lines)
        for line in line_iterator:
            if self.is_stanza(line):
                stanza = self._parse_stanza(line, line_iterator)
                self._stanzas.append(stanza)

        self._collect_logical_interfaces()
        self._connect_aliases()
        self._bridge_interfaces = self._find_bridge_ifaces()

    def _parse_stanza(self, stanza_line, iterable):
        stanza_options = []
        for line in iterable:
            line = line.strip()
            if line.startswith('#') or line == "":
                continue
            if self.is_stanza(line):
                iterable.seek(-1, True)
                break
            stanza_options.append(line)
        return Stanza(stanza_line.strip(), stanza_options)

    def stanzas(self):
        return [x for x in self._stanzas]

    def _connect_aliases(self):
        """Set a reference in the alias interfaces to its related interface"""
        for name, iface in self._logical_interfaces.items():
            if iface.is_alias:
                parent_name = name.split(':')[0]
                iface.parent = self._logical_interfaces.get(parent_name)

    def _find_bridge_ifaces(self):
        return {name: iface for (name, iface) in self._logical_interfaces.items() if iface.is_bridge}

    def _physical_interfaces(self):
        return {x.phy.name: x.phy for x in [y for y in self._stanzas if y.is_physical_interface]}

    def __iter__(self):  # class iter
        for s in self._stanzas:
            yield s

    def _is_already_bridged(self, name, bridge_port):
        iface = self._bridge_interfaces.get(name, None)
        if iface:
            return bridge_port in iface.bridge_ports
        return False

    def _collect_logical_interfaces(self):
        """
        Collects the parsed stanzas related to logical interfaces,
        populating self._logical_interfaces with a list of LogicalInterface
        objects.
        """
        physical_interfaces = self._physical_interfaces()
        logical = {}
        for s in self.stanzas():
            if s.is_logical_interface:
                stanzas = logical.get(s.name)
                if not stanzas:
                    stanzas = []
                    logical[s.name] = stanzas
                stanzas.append(s)
        make_iface = lambda name, stanzas: LogicalInterface(stanzas, name in physical_interfaces)
        self._logical_interfaces = {name: make_iface(name, stanzas) for (name, stanzas) in logical.items()}

    def bridge(self, interface_names_to_bridge, bridge_prefix, bridge_name):
        bridged_stanzas = []
        auto_stanzas_created = set()
        bridges_created = set()
        for s in self.stanzas():
            if s.is_physical_interface:
                # Handled by logical interfaces.
                continue
            elif not s.is_logical_interface:
                bridged_stanzas.append(s)
                continue

            iface = self._logical_interfaces[s.name]
            if s.name not in interface_names_to_bridge:
                # This interface is not one we want to bridge, so leave it alone.
                if iface.has_auto_stanza and s.name not in auto_stanzas_created:
                    bridged_stanzas.append(AutoStanza(s.name))
                    auto_stanzas_created.add(s.name)
                bridged_stanzas.append(s)
                continue

            existing_bridge_name = bridge_prefix + s.name
            if self._is_already_bridged(existing_bridge_name, s.name):
                # The bridge already exists, leave it alone.
                if iface.has_auto_stanza and s.name not in auto_stanzas_created:
                    bridged_stanzas.append(AutoStanza(s.name))
                    auto_stanzas_created.add(s.name)
                bridged_stanzas.append(s)
                continue

            # Bridge the interface. Make sure we only do this once.
            if s.name in bridges_created:
                continue
            bridges_created.add(s.name)
            bridged_stanzas.extend(iface._bridge(bridge_prefix, bridge_name))

        return bridged_stanzas


def uniq_append(dst, src):
    for x in src:
        if x not in dst:
            dst.append(x)
    return dst


def IfaceStanza(name, family, method, options):
    """Convenience function to create a new "iface" stanza.

Maintains original options order but removes duplicates with the
exception of 'dns-*' options which are normalised as required by
resolvconf(8) and all the dns-* options are moved to the end.

    """

    dns_search = []
    dns_nameserver = []
    dns_sortlist = []
    unique_options = []

    for o in options:
        words = o.split()
        ident = words[0]
        if ident == "dns-nameservers":
            dns_nameserver = uniq_append(dns_nameserver, words[1:])
        elif ident == "dns-search":
            dns_search = uniq_append(dns_search, words[1:])
        elif ident == "dns-sortlist":
            dns_sortlist = uniq_append(dns_sortlist, words[1:])
        elif o not in unique_options:
            unique_options.append(o)

    if dns_nameserver:
        option = "dns-nameservers " + " ".join(dns_nameserver)
        unique_options.append(option)

    if dns_search:
        option = "dns-search " + " ".join(dns_search)
        unique_options.append(option)

    if dns_sortlist:
        option = "dns-sortlist " + " ".join(dns_sortlist)
        unique_options.append(option)

    return Stanza("iface {} {} {}".format(name, family, method), unique_options)


def AutoStanza(name):
    # Convenience function to create a new "auto" stanza.
    return Stanza("auto {}".format(name))


def print_stanza(s, stream=sys.stdout):
    print(s.definition, file=stream)
    for o in s.options:
        print("   ", o, file=stream)


def print_stanzas(stanzas, stream=sys.stdout):
    n = len(stanzas)
    for i, stanza in enumerate(stanzas):
        print_stanza(stanza, stream)
        if stanza.is_logical_interface and i + 1 < n:
            print(file=stream)


def shell_cmd(s, verbose=True, exit_on_error=False, dry_run=False):
    if dry_run:
        print(s)
        return
    if verbose:
        print(s)
    p = subprocess.Popen(s, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate()
    if out and len(out) > 0:
        print(out.decode().rstrip('\n'))
    if err and len(err) > 0:
        print(err.decode().rstrip('\n'))
    if exit_on_error and retcode != 0:
        exit(1)
    return p.returncode


def arg_parser():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--bridge-prefix', help="bridge prefix", type=str, required=False, default='br-')
    parser.add_argument('--activate', help='activate new configuration', action='store_true', default=False, required=False)
    parser.add_argument('--interfaces-to-bridge', help="interfaces to bridge; space delimited", type=str, required=True)
    parser.add_argument('--dry-run', help="dry run, no activation", action='store_true', default=False, required=False)
    parser.add_argument('--bridge-name', help="bridge name", type=str, required=False)
    parser.add_argument('--reconfigure-delay', help="delay in seconds before raising interfaces", type=int, required=False, default=10)
    parser.add_argument('filename', help="interfaces(5) based filename")
    return parser


def main(args):
    interfaces = args.interfaces_to_bridge.split()

    if len(interfaces) == 0:
        sys.stderr.write("error: no interfaces specified\n")
        exit(1)

    if args.bridge_name and len(interfaces) > 1:
        sys.stderr.write("error: cannot use single bridge name '{}' against multiple interface names\n".format(args.bridge_name))
        exit(1)

    parser = NetworkInterfaceParser(args.filename)
    stanzas = parser.bridge(interfaces, args.bridge_prefix, args.bridge_name)

    if not args.activate:
        print_stanzas(stanzas)
        exit(0)

    # Dump stanzas to cur/new in-memory strings
    cur = StringIO()
    new = StringIO()
    print_stanzas(stanzas, new)
    print_stanzas(parser.stanzas(), cur)

    if cur.getvalue() == new.getvalue():
        print("already bridged, or nothing to do.")
        exit(0)

    print("**** Original configuration")
    shell_cmd("cat {}".format(args.filename), dry_run=args.dry_run)
    shell_cmd("ip -d link show", dry_run=args.dry_run)
    shell_cmd("ip route show", dry_run=args.dry_run)
    shell_cmd("brctl show", dry_run=args.dry_run)
    shell_cmd("ifdown --exclude=lo --interfaces={} {}".format(args.filename, " ".join(interfaces)), dry_run=args.dry_run)

    print("**** Activating new configuration")

    if not args.dry_run:
        with open(args.filename, 'w') as f:
            print_stanzas(stanzas, f)
            f.close()
    else:
        #print_stanzas(stanzas, sys.stdout)
        pass

    if args.reconfigure_delay and args.reconfigure_delay > 0 :
        shell_cmd("sleep {}".format(args.reconfigure_delay), dry_run=args.dry_run)
    shell_cmd("cat {}".format(args.filename), dry_run=args.dry_run)
    shell_cmd("ifup --exclude=lo --interfaces={} -a".format(args.filename), dry_run=args.dry_run)
    shell_cmd("ip -d link show", dry_run=args.dry_run)
    shell_cmd("ip route show", dry_run=args.dry_run)
    shell_cmd("brctl show", dry_run=args.dry_run)

# This script re-renders an interfaces(5) file to add a bridge to
# either all active interfaces, or a specific interface.

if __name__ == '__main__':
    sleep_preamble = os.getenv("ADD_JUJU_BRIDGE_SLEEP_PREAMBLE_FOR_TESTING", 0)
    if int(sleep_preamble) > 0:
        time.sleep(int(sleep_preamble))
    main(arg_parser().parse_args())
