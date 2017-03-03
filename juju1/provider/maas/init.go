// Copyright 2015 Canonical Ltd.
// Licensed under the AGPLv3, see LICENCE file for details.

package maas

import (
	"github.com/juju/1.25-upgrade/juju1/environs"
	"github.com/juju/1.25-upgrade/juju1/storage/provider/registry"
)

const (
	providerType = "maas"
)

func init() {
	environs.RegisterProvider(providerType, maasEnvironProvider{})

	//Register the MAAS specific storage providers.
	registry.RegisterProvider(maasStorageProviderType, &maasStorageProvider{})

	registry.RegisterEnvironStorageProviders(providerType, maasStorageProviderType)
}
