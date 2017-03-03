// Copyright 2014 Canonical Ltd.
// Licensed under the AGPLv3, see LICENCE file for details.

package backups_test

import (
	"github.com/juju/cmd"
	"github.com/juju/errors"
	gc "gopkg.in/check.v1"

	"github.com/juju/1.25-upgrade/juju1/cmd/juju/backups"
	"github.com/juju/1.25-upgrade/juju1/environs"
	"github.com/juju/1.25-upgrade/juju1/environs/bootstrap"
	"github.com/juju/1.25-upgrade/juju1/instance"
	"github.com/juju/1.25-upgrade/juju1/testing"
)

type restoreSuite struct {
	BaseBackupsSuite

	restoreCommand cmd.Command
}

var _ = gc.Suite(&restoreSuite{})

func (s *restoreSuite) SetUpTest(c *gc.C) {
	s.BaseBackupsSuite.SetUpTest(c)
}

func (s *restoreSuite) TestRestoreArgs(c *gc.C) {
	s.restoreCommand = backups.RestoreCommandForTest(nil)
	_, err := testing.RunCommand(c, s.command, "restore")
	c.Assert(err, gc.ErrorMatches, "you must specify either a file or a backup id.")

	_, err = testing.RunCommand(c, s.command, "restore", "--id", "anid", "--file", "afile")
	c.Assert(err, gc.ErrorMatches, "you must specify either a file or a backup id but not both.")

	_, err = testing.RunCommand(c, s.command, "restore", "--id", "anid", "-b")
	c.Assert(err, gc.ErrorMatches, "it is not possible to rebootstrap and restore from an id.")
}

func (s *restoreSuite) TestRestoreReboostrapControllerExists(c *gc.C) {
	fakeEnv := fakeEnviron{controllerInstances: []instance.Id{"1"}}
	s.restoreCommand = backups.RestoreCommandForTest(func() (environs.Environ, error) {
		return fakeEnv, nil
	})
	_, err := testing.RunCommand(c, s.restoreCommand, "restore", "--file", "afile", "-b")
	c.Assert(err, gc.ErrorMatches, ".*still seems to exist.*")
}

func (s *restoreSuite) TestRestoreReboostrapNoControllers(c *gc.C) {
	fakeEnv := fakeEnviron{}
	s.restoreCommand = backups.RestoreCommandForTest(func() (environs.Environ, error) {
		return fakeEnv, nil
	})
	s.PatchValue(&backups.BootstrapFunc, func(ctx environs.BootstrapContext, environ environs.Environ, args bootstrap.BootstrapParams) error {
		return errors.New("failed to bootstrap new controller")
	})

	_, err := testing.RunCommand(c, s.restoreCommand, "restore", "--file", "afile", "-b")
	c.Assert(err, gc.ErrorMatches, ".*failed to bootstrap new controller")
}

type fakeInstance struct {
	instance.Instance
	id instance.Id
}

type fakeEnviron struct {
	environs.Environ
	controllerInstances []instance.Id
}

func (f fakeEnviron) StateServerInstances() ([]instance.Id, error) {
	return f.controllerInstances, nil
}

func (f fakeEnviron) Instances(ids []instance.Id) ([]instance.Instance, error) {
	return []instance.Instance{fakeInstance{id: "1"}}, nil
}
