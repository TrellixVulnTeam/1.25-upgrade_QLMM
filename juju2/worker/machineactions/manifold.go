// Copyright 2016 Canonical Ltd.
// Copyright 2016 Cloudbase Solutions SRL
// Licensed under the AGPLv3, see LICENCE file for details.

package machineactions

import (
	"github.com/juju/1.25-upgrade/juju2/agent"
	"github.com/juju/1.25-upgrade/juju2/api/base"
	"github.com/juju/1.25-upgrade/juju2/cmd/jujud/agent/engine"
	"github.com/juju/1.25-upgrade/juju2/worker"
	"github.com/juju/1.25-upgrade/juju2/worker/dependency"
	"github.com/juju/errors"
	"gopkg.in/juju/names.v2"
)

// ManifoldConfig describes the dependencies of a machine action runner.
type ManifoldConfig struct {
	AgentName     string
	APICallerName string

	NewFacade func(base.APICaller) Facade
	NewWorker func(WorkerConfig) (worker.Worker, error)
}

// start is used by engine.AgentAPIManifold to create a StartFunc.
func (config ManifoldConfig) start(a agent.Agent, apiCaller base.APICaller) (worker.Worker, error) {
	machineTag, ok := a.CurrentConfig().Tag().(names.MachineTag)
	if !ok {
		return nil, errors.Errorf("this manifold can only be used inside a machine")
	}
	machineActionsFacade := config.NewFacade(apiCaller)
	return config.NewWorker(WorkerConfig{
		Facade:       machineActionsFacade,
		MachineTag:   machineTag,
		HandleAction: HandleAction,
	})
}

// Manifold returns a dependency.Manifold as configured.
func Manifold(config ManifoldConfig) dependency.Manifold {
	typedConfig := engine.AgentAPIManifoldConfig{
		AgentName:     config.AgentName,
		APICallerName: config.APICallerName,
	}
	return engine.AgentAPIManifold(typedConfig, config.start)
}
