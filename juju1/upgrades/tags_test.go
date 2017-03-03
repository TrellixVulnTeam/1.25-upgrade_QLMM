// Copyright 2015 Canonical Ltd.
// Licensed under the AGPLv3, see LICENCE file for details.

package upgrades_test

import (
	jc "github.com/juju/testing/checkers"
	gc "gopkg.in/check.v1"

	"github.com/juju/1.25-upgrade/juju1/environs"
	"github.com/juju/1.25-upgrade/juju1/environs/config"
	"github.com/juju/1.25-upgrade/juju1/instance"
	"github.com/juju/1.25-upgrade/juju1/state"
	statetesting "github.com/juju/1.25-upgrade/juju1/state/testing"
	"github.com/juju/1.25-upgrade/juju1/testing"
	"github.com/juju/1.25-upgrade/juju1/upgrades"
)

type tagsSuite struct {
	statetesting.StateSuite
	stateServer, unprovisioned, provisioned, container *state.Machine
}

var _ = gc.Suite(&tagsSuite{})

func (s *tagsSuite) SetUpTest(c *gc.C) {
	s.StateSuite.SetUpTest(c)

	var err error
	s.stateServer, err = s.State.AddMachine("quantal", state.JobManageEnviron)
	c.Assert(err, jc.ErrorIsNil)
	err = s.stateServer.SetProvisioned("inst-0", "nonce-0", nil)
	c.Assert(err, jc.ErrorIsNil)

	s.unprovisioned, err = s.State.AddMachine("quantal", state.JobHostUnits)
	c.Assert(err, jc.ErrorIsNil)

	s.provisioned, err = s.State.AddMachine("quantal", state.JobHostUnits)
	c.Assert(err, jc.ErrorIsNil)
	err = s.provisioned.SetProvisioned("inst-1", "nonce-1", nil)
	c.Assert(err, jc.ErrorIsNil)

	s.container, err = s.State.AddMachineInsideMachine(state.MachineTemplate{
		Series: "quantal",
		Jobs:   []state.MachineJob{state.JobHostUnits},
	}, s.provisioned.Id(), instance.LXC)
	c.Assert(err, jc.ErrorIsNil)
	err = s.container.SetProvisioned("inst-2", "nonce-2", nil)
	c.Assert(err, jc.ErrorIsNil)
}

func (s *tagsSuite) TestAddInstanceTagsSupportsTagging(c *gc.C) {
	env := &testEnvironWithTagging{
		testEnviron: testEnviron{
			cfg: testing.CustomEnvironConfig(c, testing.Attrs{
				"resource-tags": "abc=123",
			}),
		},
	}
	err := upgrades.AddInstanceTags(env, []*state.Machine{
		s.stateServer, s.unprovisioned, s.provisioned, s.container,
	})
	c.Assert(err, jc.ErrorIsNil)
	c.Assert(env.calls, jc.DeepEquals, []tagInstanceArgs{{
		"inst-0", map[string]string{
			"juju-is-state": "true",
			"juju-env-uuid": testing.EnvironmentTag.Id(),
			"abc":           "123",
		},
	}, {
		"inst-1", map[string]string{
			"juju-env-uuid": testing.EnvironmentTag.Id(),
			"abc":           "123",
		},
	}})
}

func (s *tagsSuite) TestAddInstanceTagsIgnoresManuallyProvisionedMachines(c *gc.C) {
	env := &testEnvironWithTagging{
		testEnviron: testEnviron{
			cfg: testing.CustomEnvironConfig(c, testing.Attrs{
				"resource-tags": "abc=123",
			}),
		},
	}

	manuallyProvisioned, err := s.State.AddMachine("quantal", state.JobHostUnits)
	c.Assert(err, jc.ErrorIsNil)
	err = manuallyProvisioned.SetProvisioned("inst-10", "manual:", nil)
	c.Assert(err, jc.ErrorIsNil)

	err = upgrades.AddInstanceTags(env, []*state.Machine{
		s.stateServer,
		manuallyProvisioned,
		s.provisioned})
	c.Assert(err, jc.ErrorIsNil)

	c.Assert(env.calls, jc.DeepEquals, []tagInstanceArgs{{
		// for s.stateServer
		"inst-0", map[string]string{
			"juju-is-state": "true",
			"juju-env-uuid": testing.EnvironmentTag.Id(),
			"abc":           "123",
		},
	}, // for s.provisioned
		{
			"inst-1", map[string]string{
				"juju-env-uuid": testing.EnvironmentTag.Id(),
				"abc":           "123",
			},
		}})
}

func (s *tagsSuite) TestAddInstanceTagsDoesNotSupportTagging(c *gc.C) {
	env := &testEnviron{cfg: testing.CustomEnvironConfig(c, nil)}
	err := upgrades.AddInstanceTags(env, []*state.Machine{
		s.stateServer, s.unprovisioned, s.provisioned, s.container,
	})
	c.Assert(err, jc.ErrorIsNil)
}

type testEnviron struct {
	environs.Environ
	cfg *config.Config
}

func (e *testEnviron) Config() *config.Config {
	return e.cfg
}

type tagInstanceArgs struct {
	id   instance.Id
	tags map[string]string
}

type testEnvironWithTagging struct {
	testEnviron
	calls []tagInstanceArgs
}

func (e *testEnvironWithTagging) TagInstance(id instance.Id, tags map[string]string) error {
	e.calls = append(e.calls, tagInstanceArgs{id, tags})
	return nil
}
