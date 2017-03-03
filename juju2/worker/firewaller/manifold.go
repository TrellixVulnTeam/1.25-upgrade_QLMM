// Copyright 2015 Canonical Ltd.
// Licensed under the AGPLv3, see LICENCE file for details.

package firewaller

import (
	"github.com/juju/errors"

	"github.com/juju/juju/api/base"
	"github.com/juju/juju/api/firewaller"
	"github.com/juju/juju/cmd/jujud/agent/engine"
	"github.com/juju/juju/worker"
	"github.com/juju/juju/worker/dependency"
)

// ManifoldConfig describes the resources used by the firewaller worker.
type ManifoldConfig engine.APIManifoldConfig

// Manifold returns a Manifold that encapsulates the firewaller worker.
func Manifold(config ManifoldConfig) dependency.Manifold {
	return engine.APIManifold(
		engine.APIManifoldConfig(config),
		manifoldStart,
	)
}

// manifoldStart creates a firewaller worker, given a base.APICaller.
func manifoldStart(apiCaller base.APICaller) (worker.Worker, error) {
	api := firewaller.NewState(apiCaller)
	w, err := NewFirewaller(api)
	if err != nil {
		return nil, errors.Trace(err)
	}
	return w, nil
}
