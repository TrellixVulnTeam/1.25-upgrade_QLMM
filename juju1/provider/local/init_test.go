// Copyright 2015 Canonical Ltd.
// Licensed under the AGPLv3, see LICENCE file for details.

package local_test

import (
	jc "github.com/juju/testing/checkers"
	gc "gopkg.in/check.v1"

	"github.com/juju/1.25-upgrade/juju1/storage"
	"github.com/juju/1.25-upgrade/juju1/storage/provider"
	"github.com/juju/1.25-upgrade/juju1/storage/provider/registry"
	"github.com/juju/1.25-upgrade/juju1/testing"
)

type providerSuite struct {
	testing.BaseSuite
}

var _ = gc.Suite(&providerSuite{})

func (*providerSuite) TestSupportedProviders(c *gc.C) {
	supported := []storage.ProviderType{provider.HostLoopProviderType}
	for _, providerType := range supported {
		ok := registry.IsProviderSupported("local", providerType)
		c.Assert(ok, jc.IsTrue)
	}
}
