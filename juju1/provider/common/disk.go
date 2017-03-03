// Copyright 2014 Canonical Ltd.
// Licensed under the AGPLv3, see LICENCE file for details.

package common

import (
	"github.com/juju/1.25-upgrade/juju1/version"
)

// MinRootDiskSizeGiB is the minimum size for the root disk of an
// instance, in Gigabytes. This value accommodates the anticipated
// size of the initial image, any updates, and future application
// data.
func MinRootDiskSizeGiB(ser string) uint64 {
	// See comment below that explains why we're ignoring the error
	os, _ := version.GetOSFromSeries(ser)
	switch os {
	case version.Ubuntu, version.CentOS:
		return 8
	case version.Windows:
		return 40
	// By default we just return a "sane" default, since the error will just
	// be returned by the api and seen in juju status
	default:
		return 8
	}
}

// MiBToGiB converts the provided megabytes (base-2) into the nearest
// gigabytes (base-2), rounding up. This is useful for providers that
// deal in gigabytes (while juju deals in megabytes).
func MiBToGiB(m uint64) uint64 {
	return (m + 1023) / 1024
}
