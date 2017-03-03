// Copyright 2015 Canonical Ltd.
// Licensed under the AGPLv3, see LICENCE file for details.

// +build go1.3

package lxdclient

import (
	"github.com/juju/errors"
	"github.com/lxc/lxd/shared/api"
)

type rawConfigClient interface {
	Addresses() ([]string, error)
	SetServerConfig(key, value string) (*api.Response, error)
	SetContainerConfig(container, key, value string) error

	WaitForSuccess(waitURL string) error
	ServerStatus() (*api.Server, error)
}

type configClient struct {
	raw rawConfigClient
}

// SetServerConfig sets the given value in the server's config.
func (c configClient) SetServerConfig(key, value string) error {
	resp, err := c.raw.SetServerConfig(key, value)
	if err != nil {
		return errors.Trace(err)
	}

	if resp.Operation != "" {
		if err := c.raw.WaitForSuccess(resp.Operation); err != nil {
			// TODO(ericsnow) Handle different failures (from the async
			// operation) differently?
			return errors.Trace(err)
		}
	}

	return nil
}

// SetContainerConfig sets the given config value for the specified
// container.
func (c configClient) SetContainerConfig(container, key, value string) error {
	return errors.Trace(c.raw.SetContainerConfig(container, key, value))
}

// ServerStatus reports the state of the server.
func (c configClient) ServerStatus() (*api.Server, error) {
	return c.raw.ServerStatus()
}

// ServerAddresses reports the addresses that the server is listening on.
func (c configClient) ServerAddresses() ([]string, error) {
	return c.raw.Addresses()
}
