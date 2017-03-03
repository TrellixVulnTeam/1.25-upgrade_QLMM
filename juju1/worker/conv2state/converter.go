// Copyright 2015 Canonical Ltd.
// Licensed under the AGPLv3, see LICENCE file for details.

package conv2state

import (
	"github.com/juju/errors"
	"github.com/juju/loggo"
	"github.com/juju/names"

	apimachiner "github.com/juju/1.25-upgrade/juju1/api/machiner"
	"github.com/juju/1.25-upgrade/juju1/api/watcher"
	"github.com/juju/1.25-upgrade/juju1/apiserver/params"
	"github.com/juju/1.25-upgrade/juju1/cmd/jujud/util"
	"github.com/juju/1.25-upgrade/juju1/state/multiwatcher"
	"github.com/juju/1.25-upgrade/juju1/worker"
)

var logger = loggo.GetLogger("juju.worker.conv2state")

// New returns a new notify watch handler that will convert the given machine &
// agent to a state server.
func New(m *apimachiner.State, agent Agent) worker.NotifyWatchHandler {
	return &converter{machiner: wrapper{m}, agent: agent}
}

// converter is a NotifyWatchHandler that converts a unit hosting machine to a
// state machine.
type converter struct {
	agent    Agent
	machiner machiner
	machine  machine
}

// Agent is an interface that exposes machine agent methods required for the
// conversion worker.
type Agent interface {
	Tag() names.Tag
}

// machiner is a type that creates machines from a tag.
type machiner interface {
	Machine(tag names.MachineTag) (machine, error)
}

// machine is a type that has a list of jobs and can be watched.
type machine interface {
	Jobs() (*params.JobsResult, error)
	Watch() (watcher.NotifyWatcher, error)
}

// wrapper is a wrapper around api/machiner.State to match the (local) machiner
// interface.
type wrapper struct {
	m *apimachiner.State
}

// Machines implements machiner.Machine and returns a machine from the wrapper
// api/machiner.
func (w wrapper) Machine(tag names.MachineTag) (machine, error) {
	m, err := w.m.Machine(tag)
	if err != nil {
		return nil, err
	}
	return m, nil
}

// SetUp implements NotifyWatchHandler's SetUp method. It returns a watcher that
// checks for changes to the current machine.
func (c *converter) SetUp() (watcher.NotifyWatcher, error) {
	m, err := c.machiner.Machine(c.agent.Tag().(names.MachineTag))
	if err != nil {
		return nil, errors.Trace(err)
	}
	c.machine = m
	return m.Watch()
}

// Handle implements NotifyWatchHandler's Handle method.  If the change means
// that the machine is now expected to manage the environment,
// we throw a fatal error to instigate agent restart.
func (c *converter) Handle(_ <-chan struct{}) error {
	results, err := c.machine.Jobs()
	if err != nil {
		return errors.Annotate(err, "can't get jobs for machine")
	}
	if !multiwatcher.AnyJobNeedsState(results.Jobs...) {
		return nil
	}
	return &util.FatalError{"bounce agent to pick up new jobs"}
}

// TearDown implements NotifyWatchHandler's TearDown method.
func (c *converter) TearDown() error {
	return nil
}
