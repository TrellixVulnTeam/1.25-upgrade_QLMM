// Copyright 2016 Canonical Ltd.
// Licensed under the AGPLv3, see LICENCE file for details.

package proxyupdater

import (
	"github.com/juju/1.25-upgrade/juju1/environs/config"
	"github.com/juju/1.25-upgrade/juju1/network"
	"github.com/juju/1.25-upgrade/juju1/state"
)

// stateShim forwards and adapts state.State methods to Backend
type stateShim struct {
	Backend
	st *state.State
}

func (s *stateShim) EnvironConfig() (*config.Config, error) {
	return s.st.EnvironConfig()
}

func (s *stateShim) APIHostPorts() ([][]network.HostPort, error) {
	return s.st.APIHostPorts()
}

func (s *stateShim) WatchAPIHostPorts() state.NotifyWatcher {
	return s.st.WatchAPIHostPorts()
}

func (s *stateShim) WatchForEnvironConfigChanges() state.NotifyWatcher {
	return s.st.WatchForEnvironConfigChanges()
}
