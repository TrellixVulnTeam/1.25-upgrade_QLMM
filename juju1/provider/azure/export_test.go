// Copyright 2015 Canonical Ltd.
// Licensed under the AGPLv3, see LICENCE file for details.

package azure

import (
	gc "gopkg.in/check.v1"

	"github.com/juju/1.25-upgrade/juju1/environs"
)

var MakeUserdataResourceScripts = makeUserdataResourceScripts

func MakeEnvironForTest(c *gc.C) environs.Environ {
	return makeEnviron(c)
}
