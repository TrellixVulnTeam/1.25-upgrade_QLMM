// Copyright 2016 Canonical Ltd.
// Licensed under the AGPLv3, see LICENCE file for details.

package proxyupdater

import (
	"strings"

	"github.com/juju/1.25-upgrade/juju1/apiserver/common"
	"github.com/juju/1.25-upgrade/juju1/apiserver/params"
	"github.com/juju/1.25-upgrade/juju1/environs/config"
	"github.com/juju/1.25-upgrade/juju1/network"
	"github.com/juju/1.25-upgrade/juju1/state"
	"github.com/juju/1.25-upgrade/juju1/state/watcher"
	"github.com/juju/utils/set"
)

func init() {
	common.RegisterStandardFacade("ProxyUpdater", 1, NewAPI)
}

// API defines the methods the ProxyUpdater API facade implements.
type API interface {
	WatchForProxyConfigAndAPIHostPortChanges() (params.NotifyWatchResult, error)
	ProxyConfig() (params.ProxyConfigResult, error)
}

// Backend defines the state methods this facade needs, so they can be
// mocked for testing.
type Backend interface {
	EnvironConfig() (*config.Config, error)
	APIHostPorts() ([][]network.HostPort, error)
	WatchAPIHostPorts() state.NotifyWatcher
	WatchForEnvironConfigChanges() state.NotifyWatcher
}

type proxyUpdaterAPI struct {
	st         Backend
	resources  *common.Resources
	authorizer common.Authorizer
}

// NewAPI creates a new API server-side facade with a state.State backing.
func NewAPI(st *state.State, res *common.Resources, auth common.Authorizer) (API, error) {
	return newAPIWithBacking(&stateShim{st: st}, res, auth)
}

// newAPIWithBacking creates a new server-side API facade with the given Backing.
func newAPIWithBacking(st Backend, resources *common.Resources, authorizer common.Authorizer) (API, error) {
	if !(authorizer.AuthMachineAgent() || authorizer.AuthUnitAgent()) {
		return nil, common.ErrPerm
	}
	return &proxyUpdaterAPI{
		st:         st,
		resources:  resources,
		authorizer: authorizer,
	}, nil
}

// WatchChanges watches for cleanups to be perfomed in state
func (api *proxyUpdaterAPI) WatchForProxyConfigAndAPIHostPortChanges() (params.NotifyWatchResult, error) {
	watch := common.NewMultiNotifyWatcher(
		api.st.WatchForEnvironConfigChanges(),
		api.st.WatchAPIHostPorts())
	if _, ok := <-watch.Changes(); ok {
		return params.NotifyWatchResult{
			NotifyWatcherId: api.resources.Register(watch),
		}, nil
	}
	return params.NotifyWatchResult{
		Error: common.ServerError(watcher.EnsureErr(watch)),
	}, nil
}

func (api *proxyUpdaterAPI) ProxyConfig() (params.ProxyConfigResult, error) {
	var cfg params.ProxyConfigResult
	env, err := api.st.EnvironConfig()
	if err != nil {
		return cfg, err
	}

	apiHostPorts, err := api.st.APIHostPorts()
	if err != nil {
		return cfg, err
	}

	cfg.ProxySettings = env.ProxySettings()
	cfg.APTProxySettings = env.AptProxySettings()

	var noProxy []string
	if cfg.ProxySettings.NoProxy != "" {
		noProxy = strings.Split(cfg.ProxySettings.NoProxy, ",")
	}

	noProxySet := set.NewStrings(noProxy...)

	for _, host := range apiHostPorts {
		for _, hp := range host {
			noProxySet.Add(hp.Address.Value)
		}
	}

	cfg.ProxySettings.NoProxy = strings.Join(noProxySet.SortedValues(), ",")
	return cfg, nil
}
