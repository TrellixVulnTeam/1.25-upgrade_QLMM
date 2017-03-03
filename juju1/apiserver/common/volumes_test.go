// Copyright 2015 Canonical Ltd.
// Licensed under the AGPLv3, see LICENCE file for details.

package common_test

import (
	"github.com/juju/names"
	jc "github.com/juju/testing/checkers"
	gc "gopkg.in/check.v1"

	"github.com/juju/1.25-upgrade/juju1/apiserver/common"
	"github.com/juju/1.25-upgrade/juju1/apiserver/params"
	"github.com/juju/1.25-upgrade/juju1/environs/tags"
	"github.com/juju/1.25-upgrade/juju1/state"
	"github.com/juju/1.25-upgrade/juju1/testing"
)

type volumesSuite struct{}

var _ = gc.Suite(&volumesSuite{})

func (s *volumesSuite) TestVolumeParams(c *gc.C) {
	s.testVolumeParams(c, &state.VolumeParams{
		Pool: "loop",
		Size: 1024,
	}, nil)
}

func (s *volumesSuite) TestVolumeParamsAlreadyProvisioned(c *gc.C) {
	s.testVolumeParams(c, nil, &state.VolumeInfo{
		Pool: "loop",
		Size: 1024,
	})
}

func (*volumesSuite) testVolumeParams(c *gc.C, volumeParams *state.VolumeParams, info *state.VolumeInfo) {
	tag := names.NewVolumeTag("100")
	p, err := common.VolumeParams(
		&fakeVolume{tag: tag, params: volumeParams, info: info},
		nil, // StorageInstance
		testing.CustomEnvironConfig(c, testing.Attrs{
			"resource-tags": "a=b c=",
		}),
		&fakePoolManager{},
	)
	c.Assert(err, jc.ErrorIsNil)
	c.Assert(p, jc.DeepEquals, params.VolumeParams{
		VolumeTag: "volume-100",
		Provider:  "loop",
		Size:      1024,
		Tags: map[string]string{
			tags.JujuEnv: testing.EnvironmentTag.Id(),
			"a":          "b",
			"c":          "",
		},
	})
}

func (*volumesSuite) TestVolumeParamsStorageTags(c *gc.C) {
	volumeTag := names.NewVolumeTag("100")
	storageTag := names.NewStorageTag("mystore/0")
	unitTag := names.NewUnitTag("mysql/123")
	p, err := common.VolumeParams(
		&fakeVolume{tag: volumeTag, params: &state.VolumeParams{
			Pool: "loop", Size: 1024,
		}},
		&fakeStorageInstance{tag: storageTag, owner: unitTag},
		testing.CustomEnvironConfig(c, nil),
		&fakePoolManager{},
	)
	c.Assert(err, jc.ErrorIsNil)
	c.Assert(p, jc.DeepEquals, params.VolumeParams{
		VolumeTag: "volume-100",
		Provider:  "loop",
		Size:      1024,
		Tags: map[string]string{
			tags.JujuEnv:             testing.EnvironmentTag.Id(),
			tags.JujuStorageInstance: "mystore/0",
			tags.JujuStorageOwner:    "mysql/123",
		},
	})
}
