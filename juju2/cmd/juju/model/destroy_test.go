// Copyright 2015 Canonical Ltd.
// Licensed under the AGPLv3, see LICENCE file for details.

package model_test

import (
	"bytes"
	"time"

	"github.com/juju/cmd"
	"github.com/juju/errors"
	jc "github.com/juju/testing/checkers"
	gc "gopkg.in/check.v1"
	"gopkg.in/juju/names.v2"

	"github.com/juju/juju/api/base"
	"github.com/juju/juju/apiserver/common"
	"github.com/juju/juju/apiserver/params"
	"github.com/juju/juju/cmd/juju/model"
	"github.com/juju/juju/cmd/modelcmd"
	cmdtesting "github.com/juju/juju/cmd/testing"
	"github.com/juju/juju/jujuclient"
	"github.com/juju/juju/jujuclient/jujuclienttesting"
	_ "github.com/juju/juju/provider/dummy"
	"github.com/juju/juju/testing"
)

type DestroySuite struct {
	testing.FakeJujuXDGDataHomeSuite
	api   *fakeAPI
	store *jujuclienttesting.MemStore
	sleep func(time.Duration)
}

var _ = gc.Suite(&DestroySuite{})

// fakeDestroyAPI mocks out the cient API
type fakeAPI struct {
	err             error
	env             map[string]interface{}
	statusCallCount int
	modelInfoErr    []*params.Error
}

func (f *fakeAPI) Close() error { return nil }

func (f *fakeAPI) DestroyModel(names.ModelTag) error {
	return f.err
}

func (f *fakeAPI) ModelStatus(models ...names.ModelTag) ([]base.ModelStatus, error) {
	var err *params.Error = &params.Error{Code: params.CodeNotFound}
	if f.statusCallCount < len(f.modelInfoErr) {
		err = f.modelInfoErr[f.statusCallCount]
	}
	f.statusCallCount++
	return []base.ModelStatus{{}}, err
}

func (s *DestroySuite) SetUpTest(c *gc.C) {
	s.FakeJujuXDGDataHomeSuite.SetUpTest(c)
	s.api = &fakeAPI{}
	s.api.err = nil

	s.store = jujuclienttesting.NewMemStore()
	s.store.CurrentControllerName = "test1"
	s.store.Controllers["test1"] = jujuclient.ControllerDetails{ControllerUUID: "test1-uuid"}
	s.store.Models["test1"] = &jujuclient.ControllerModels{
		Models: map[string]jujuclient.ModelDetails{
			"admin/test1": {"test1-uuid"},
			"admin/test2": {"test2-uuid"},
		},
	}
	s.store.Accounts["test1"] = jujuclient.AccountDetails{
		User: "admin",
	}
	s.sleep = func(time.Duration) {}
}

func (s *DestroySuite) runDestroyCommand(c *gc.C, args ...string) (*cmd.Context, error) {
	cmd := model.NewDestroyCommandForTest(s.api, noOpRefresh, s.store, s.sleep)
	return testing.RunCommand(c, cmd, args...)
}

func (s *DestroySuite) NewDestroyCommand() cmd.Command {
	return model.NewDestroyCommandForTest(s.api, noOpRefresh, s.store, s.sleep)
}

func checkModelExistsInStore(c *gc.C, name string, store jujuclient.ClientStore) {
	controller, model := modelcmd.SplitModelName(name)
	_, err := store.ModelByName(controller, model)
	c.Assert(err, jc.ErrorIsNil)
}

func checkModelRemovedFromStore(c *gc.C, name string, store jujuclient.ClientStore) {
	controller, model := modelcmd.SplitModelName(name)
	_, err := store.ModelByName(controller, model)
	c.Assert(err, jc.Satisfies, errors.IsNotFound)
}

func (s *DestroySuite) TestDestroyNoModelNameError(c *gc.C) {
	_, err := s.runDestroyCommand(c)
	c.Assert(err, gc.ErrorMatches, "no model specified")
}

func (s *DestroySuite) TestDestroyBadFlags(c *gc.C) {
	_, err := s.runDestroyCommand(c, "-n")
	c.Assert(err, gc.ErrorMatches, "flag provided but not defined: -n")
}

func (s *DestroySuite) TestDestroyUnknownArgument(c *gc.C) {
	_, err := s.runDestroyCommand(c, "model", "whoops")
	c.Assert(err, gc.ErrorMatches, `unrecognized args: \["whoops"\]`)
}

func (s *DestroySuite) TestDestroyUnknownModelCallsRefresh(c *gc.C) {
	called := false
	refresh := func(jujuclient.ClientStore, string) error {
		called = true
		return nil
	}

	cmd := model.NewDestroyCommandForTest(s.api, refresh, s.store, s.sleep)
	_, err := testing.RunCommand(c, cmd, "foo")
	c.Check(called, jc.IsTrue)
	c.Check(err, gc.ErrorMatches, `cannot read model info: model test1:admin/foo not found`)
}

func (s *DestroySuite) TestDestroyCannotConnectToAPI(c *gc.C) {
	s.api.err = errors.New("connection refused")
	_, err := s.runDestroyCommand(c, "test2", "-y")
	c.Assert(err, gc.ErrorMatches, "cannot destroy model: connection refused")
	c.Check(c.GetTestLog(), jc.Contains, "failed to destroy model \"test2\"")
	checkModelExistsInStore(c, "test1:admin/test2", s.store)
}

func (s *DestroySuite) TestSystemDestroyFails(c *gc.C) {
	_, err := s.runDestroyCommand(c, "test1", "-y")
	c.Assert(err, gc.ErrorMatches, `"test1" is a controller; use 'juju destroy-controller' to destroy it`)
	checkModelExistsInStore(c, "test1:admin/test1", s.store)
}

func (s *DestroySuite) TestDestroy(c *gc.C) {
	checkModelExistsInStore(c, "test1:admin/test2", s.store)
	_, err := s.runDestroyCommand(c, "test2", "-y")
	c.Assert(err, jc.ErrorIsNil)
	checkModelRemovedFromStore(c, "test1:admin/test2", s.store)
}

func (s *DestroySuite) TestDestroyBlocks(c *gc.C) {
	checkModelExistsInStore(c, "test1:admin/test2", s.store)
	s.api.modelInfoErr = []*params.Error{{}, {Code: params.CodeNotFound}}
	_, err := s.runDestroyCommand(c, "test2", "-y")
	c.Assert(err, jc.ErrorIsNil)
	checkModelRemovedFromStore(c, "test1:admin/test2", s.store)
	c.Assert(s.api.statusCallCount, gc.Equals, 1)
}

func (s *DestroySuite) TestFailedDestroyModel(c *gc.C) {
	s.api.err = errors.New("permission denied")
	_, err := s.runDestroyCommand(c, "test1:test2", "-y")
	c.Assert(err, gc.ErrorMatches, "cannot destroy model: permission denied")
	checkModelExistsInStore(c, "test1:admin/test2", s.store)
}

func (s *DestroySuite) resetModel(c *gc.C) {
	s.store.Models["test1"] = &jujuclient.ControllerModels{
		Models: map[string]jujuclient.ModelDetails{
			"admin/test1": {"test1-uuid"},
			"admin/test2": {"test2-uuid"},
		},
	}
}

func (s *DestroySuite) TestDestroyCommandConfirmation(c *gc.C) {
	var stdin, stdout bytes.Buffer
	ctx, err := cmd.DefaultContext()
	c.Assert(err, jc.ErrorIsNil)
	ctx.Stdout = &stdout
	ctx.Stdin = &stdin

	// Ensure confirmation is requested if "-y" is not specified.
	stdin.WriteString("n")
	_, errc := cmdtesting.RunCommand(ctx, s.NewDestroyCommand(), "test2")
	select {
	case err := <-errc:
		c.Check(err, gc.ErrorMatches, "model destruction: aborted")
	case <-time.After(testing.LongWait):
		c.Fatalf("command took too long")
	}
	c.Check(testing.Stdout(ctx), gc.Matches, "WARNING!.*test2(.|\n)*")
	checkModelExistsInStore(c, "test1:admin/test1", s.store)

	// EOF on stdin: equivalent to answering no.
	stdin.Reset()
	stdout.Reset()
	_, errc = cmdtesting.RunCommand(ctx, s.NewDestroyCommand(), "test2")
	select {
	case err := <-errc:
		c.Check(err, gc.ErrorMatches, "model destruction: aborted")
	case <-time.After(testing.LongWait):
		c.Fatalf("command took too long")
	}
	c.Check(testing.Stdout(ctx), gc.Matches, "WARNING!.*test2(.|\n)*")
	checkModelExistsInStore(c, "test1:admin/test2", s.store)

	for _, answer := range []string{"y", "Y", "yes", "YES"} {
		stdin.Reset()
		stdout.Reset()
		stdin.WriteString(answer)
		_, errc = cmdtesting.RunCommand(ctx, s.NewDestroyCommand(), "test2")
		select {
		case err := <-errc:
			c.Check(err, jc.ErrorIsNil)
		case <-time.After(testing.LongWait):
			c.Fatalf("command took too long")
		}
		checkModelRemovedFromStore(c, "test1:admin/test2", s.store)

		// Add the test2 model back into the store for the next test
		s.resetModel(c)
	}
}

func (s *DestroySuite) TestBlockedDestroy(c *gc.C) {
	s.api.err = common.OperationBlockedError("TestBlockedDestroy")
	_, err := s.runDestroyCommand(c, "test2", "-y")
	testing.AssertOperationWasBlocked(c, err, ".*TestBlockedDestroy.*")
}
