// Copyright 2015 Canonical Ltd.
// Licensed under the AGPLv3, see LICENCE file for details.

package proxyupdater

import (
	"github.com/juju/1.25-upgrade/juju1/api/base"
	"github.com/juju/1.25-upgrade/juju1/worker"
	"github.com/juju/1.25-upgrade/juju1/worker/dependency"
	"github.com/juju/1.25-upgrade/juju1/worker/util"
)

// ManifoldConfig defines the names of the manifolds on which a Manifold will depend.
type ManifoldConfig util.ApiManifoldConfig

// Manifold returns a dependency manifold that runs a proxy updater worker,
// using the api connection resource named in the supplied config.
func Manifold(config ManifoldConfig) dependency.Manifold {
	return util.ApiManifold(util.ApiManifoldConfig(config), newWorker)
}

// newWorker is not currently tested; it should eventually replace New as the
// package's exposed factory func, and then all tests should pass through it.
func newWorker(apiCaller base.APICaller) (worker.Worker, error) {
	return New(apiCaller, false), nil
}
