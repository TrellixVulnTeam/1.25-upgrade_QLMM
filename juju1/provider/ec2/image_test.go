// Copyright 2011, 2012, 2013 Canonical Ltd.
// Licensed under the AGPLv3, see LICENCE file for details.

package ec2

import (
	"fmt"

	jc "github.com/juju/testing/checkers"
	"github.com/juju/utils"
	"github.com/juju/utils/series"
	gc "gopkg.in/check.v1"

	"github.com/juju/1.25-upgrade/juju1/constraints"
	"github.com/juju/1.25-upgrade/juju1/environs/imagemetadata"
	imagetesting "github.com/juju/1.25-upgrade/juju1/environs/imagemetadata/testing"
	"github.com/juju/1.25-upgrade/juju1/environs/instances"
	"github.com/juju/1.25-upgrade/juju1/environs/simplestreams"
	"github.com/juju/1.25-upgrade/juju1/testing"
)

var _ = gc.Suite(&specSuite{})

type specSuite struct {
	testing.BaseSuite
}

func (s *specSuite) SetUpSuite(c *gc.C) {
	s.BaseSuite.SetUpSuite(c)
	imagetesting.PatchOfficialDataSources(&s.CleanupSuite, "test:")
	UseTestImageData(TestImagesData)
	UseTestInstanceTypeData(TestInstanceTypeCosts)
	UseTestRegionData(TestRegions)
}

func (s *specSuite) TearDownSuite(c *gc.C) {
	UseTestInstanceTypeData(nil)
	UseTestImageData(nil)
	UseTestRegionData(nil)
	s.BaseSuite.TearDownSuite(c)
}

var findInstanceSpecTests = []struct {
	series  string
	arches  []string
	cons    string
	itype   string
	image   string
	storage []string
}{
	{
		series: "xenial",
		arches: []string{"amd64"},
		itype:  "m3.medium",
		image:  "ami-00000133",
	}, {
		series: "quantal",
		arches: []string{"i386"},
		itype:  "c1.medium",
		image:  "ami-01000034",
	}, {
		series: "xenial",
		arches: []string{"amd64"},
		cons:   "cpu-cores=4",
		itype:  "m3.xlarge",
		image:  "ami-00000133",
	}, {
		series: "xenial",
		arches: []string{"amd64"},
		cons:   "mem=10G",
		itype:  "m3.xlarge",
		image:  "ami-00000133",
	}, {
		series: "xenial",
		arches: []string{"amd64"},
		cons:   "mem=",
		itype:  "m3.medium",
		image:  "ami-00000133",
	}, {
		series: "xenial",
		arches: []string{"amd64"},
		cons:   "cpu-power=",
		itype:  "m3.medium",
		image:  "ami-00000133",
	}, {
		series: "xenial",
		arches: []string{"amd64"},
		cons:   "cpu-power=800",
		itype:  "m3.xlarge",
		image:  "ami-00000133",
	}, {
		series: "xenial",
		arches: []string{"amd64"},
		cons:   "instance-type=m1.medium cpu-power=200",
		itype:  "m1.medium",
		image:  "ami-00000133",
	}, {
		series: "xenial",
		arches: []string{"amd64"},
		cons:   "mem=2G root-disk=16384M",
		itype:  "m3.medium",
		image:  "ami-00000133",
	}, {
		series:  "xenial",
		arches:  []string{"amd64"},
		cons:    "mem=4G root-disk=16384M",
		itype:   "m3.large",
		storage: []string{"ssd", "ebs"},
		image:   "ami-00000133",
	}, {
		series:  "xenial",
		arches:  []string{"amd64"},
		cons:    "mem=4G root-disk=16384M",
		itype:   "m3.large",
		storage: []string{"ebs", "ssd"},
		image:   "ami-00000139",
	}, {
		series:  "xenial",
		arches:  []string{"amd64"},
		cons:    "mem=4G root-disk=16384M",
		itype:   "m3.large",
		storage: []string{"ebs"},
		image:   "ami-00000139",
	}, {
		series: "trusty",
		arches: []string{"amd64"},
		itype:  "m3.medium",
		image:  "ami-00000033",
	}, {
		series: "quantal",
		arches: []string{"i386"},
		itype:  "c1.medium",
		image:  "ami-01000034",
	}, {
		series: "quantal",
		arches: both,
		cons:   "arch=amd64",
		itype:  "cc2.8xlarge",
		image:  "ami-01000035",
	}, {
		series: "quantal",
		arches: both,
		cons:   "instance-type=cc2.8xlarge",
		itype:  "cc2.8xlarge",
		image:  "ami-01000035",
	}, {
		series: "trusty",
		arches: []string{"i386"},
		cons:   "instance-type=c1.medium",
		itype:  "c1.medium",
		image:  "ami-00000034",
	}}

func (s *specSuite) TestFindInstanceSpec(c *gc.C) {
	for i, test := range findInstanceSpecTests {
		c.Logf("\ntest %d: %q; %q; %q; %v", i, test.series, test.arches, test.cons, test.storage)
		stor := test.storage
		if len(stor) == 0 {
			stor = []string{ssdStorage, ebsStorage}
		}
		spec, err := findInstanceSpec(
			[]simplestreams.DataSource{
				simplestreams.NewURLDataSource("test", "test:", utils.VerifySSLHostnames)},
			"released",
			&instances.InstanceConstraint{
				Region:      "test",
				Series:      test.series,
				Arches:      test.arches,
				Constraints: constraints.MustParse(test.cons),
				Storage:     stor,
			})
		c.Assert(err, jc.ErrorIsNil)
		c.Check(spec.InstanceType.Name, gc.Equals, test.itype)
		c.Check(spec.Image.Id, gc.Equals, test.image)
	}
}

func (s *specSuite) TestFindInstanceSpecNotSetCpuPowerWhenInstanceTypeSet(c *gc.C) {

	source := []simplestreams.DataSource{
		simplestreams.NewURLDataSource("test", "test:", utils.VerifySSLHostnames),
	}
	instanceConstraint := &instances.InstanceConstraint{
		Region:      "test",
		Series:      series.LatestLts(),
		Constraints: constraints.MustParse("instance-type=t2.medium"),
	}

	c.Check(instanceConstraint.Constraints.CpuPower, gc.IsNil)
	findInstanceSpec(source, "released", instanceConstraint)

	c.Check(instanceConstraint.Constraints.CpuPower, gc.IsNil)
}

var findInstanceSpecErrorTests = []struct {
	series string
	arches []string
	cons   string
	err    string
}{
	{
		series: "bad",
		arches: both,
		err:    `unknown version for series: "bad"`,
	}, {
		series: series.LatestLts(),
		arches: []string{"arm"},
		err:    fmt.Sprintf(`no \%q\ images in test with arches \[arm\]`, series.LatestLts()),
	}, {
		series: "raring",
		arches: both,
		cons:   "mem=4G",
		err:    `no "raring" images in test matching instance types \[m3.large m3.xlarge c1.xlarge m3.2xlarge cc2.8xlarge\]`,
	}, {
		series: series.LatestLts(),
		arches: both,
		cons:   "instance-type=m1.small mem=4G",
		err:    `no instance types in test matching constraints "instance-type=m1.small mem=4096M"`,
	},
}

func (s *specSuite) TestFindInstanceSpecErrors(c *gc.C) {
	for i, t := range findInstanceSpecErrorTests {
		c.Logf("test %d", i)
		_, err := findInstanceSpec(
			[]simplestreams.DataSource{
				simplestreams.NewURLDataSource("test", "test:", utils.VerifySSLHostnames)},
			"released",
			&instances.InstanceConstraint{
				Region:      "test",
				Series:      t.series,
				Arches:      t.arches,
				Constraints: constraints.MustParse(t.cons),
			})
		c.Check(err, gc.ErrorMatches, t.err)
	}
}

func (*specSuite) TestFilterImagesAcceptsNil(c *gc.C) {
	c.Check(filterImages(nil, nil), gc.HasLen, 0)
}

func (*specSuite) TestFilterImagesReturnsSelectively(c *gc.C) {
	good := imagemetadata.ImageMetadata{Id: "good", Storage: "ebs"}
	bad := imagemetadata.ImageMetadata{Id: "bad", Storage: "ftp"}
	input := []*imagemetadata.ImageMetadata{&good, &bad}
	expectation := []*imagemetadata.ImageMetadata{&good}

	ic := &instances.InstanceConstraint{Storage: []string{"ebs"}}
	c.Check(filterImages(input, ic), gc.DeepEquals, expectation)
}

func (*specSuite) TestFilterImagesMaintainsOrdering(c *gc.C) {
	input := []*imagemetadata.ImageMetadata{
		{Id: "one", Storage: "ebs"},
		{Id: "two", Storage: "ebs"},
		{Id: "three", Storage: "ebs"},
	}
	ic := &instances.InstanceConstraint{Storage: []string{"ebs"}}
	c.Check(filterImages(input, ic), gc.DeepEquals, input)
}
