// Copyright 2016 Canonical Ltd.
// Licensed under the AGPLv3, see LICENCE file for details.

// +build go1.3

package lxdclient_test

import (
	"errors"

	"github.com/juju/testing"
	jc "github.com/juju/testing/checkers"
	"github.com/lxc/lxd/shared/api"
	gc "gopkg.in/check.v1"

	"github.com/juju/juju/tools/lxdclient"
)

var (
	_ = gc.Suite(&utilsSuite{})
)

type utilsSuite struct {
	lxdclient.BaseSuite
}

func (s *utilsSuite) TestEnableHTTPSListener(c *gc.C) {
	client := newMockConfigSetter()
	err := lxdclient.EnableHTTPSListener(client)
	c.Assert(err, jc.ErrorIsNil)
	client.CheckCall(c, 0, "ServerStatus")
	client.CheckCall(c, 1, "SetServerConfig", "core.https_address", "[::]")
}

func (s *utilsSuite) TestEnableHTTPSListenerAlreadyEnabled(c *gc.C) {
	client := newMockConfigSetter()
	client.ServerState.Config["core.https_address"] = "foo"
	err := lxdclient.EnableHTTPSListener(client)
	c.Assert(err, jc.ErrorIsNil)
	client.CheckCallNames(c, "ServerStatus")
}

func (s *utilsSuite) TestEnableHTTPSListenerError(c *gc.C) {
	client := newMockConfigSetter()
	client.SetErrors(errors.New("uh oh"))
	err := lxdclient.EnableHTTPSListener(client)
	c.Assert(err, gc.ErrorMatches, "uh oh")
}

func (s *utilsSuite) TestEnableHTTPSListenerIPV4Fallback(c *gc.C) {
	client := newMockConfigSetter()
	client.SetErrors(nil, errors.New("any error string added by lxd: socket: address family not supported by protocol"))
	err := lxdclient.EnableHTTPSListener(client)
	c.Assert(err, jc.ErrorIsNil)
	client.CheckCall(c, 0, "ServerStatus")
	client.CheckCall(c, 1, "SetServerConfig", "core.https_address", "[::]")
	client.CheckCall(c, 2, "SetServerConfig", "core.https_address", "0.0.0.0")
}

type mockConfigSetter struct {
	testing.Stub
	ServerState *api.Server
}

func newMockConfigSetter() *mockConfigSetter {
	return &mockConfigSetter{
		ServerState: &api.Server{
			ServerPut: api.ServerPut{
				Config: map[string]interface{}{},
			},
		},
	}
}

func (m *mockConfigSetter) ServerStatus() (*api.Server, error) {
	m.MethodCall(m, "ServerStatus")
	return m.ServerState, m.NextErr()
}

func (m *mockConfigSetter) SetServerConfig(k, v string) error {
	m.MethodCall(m, "SetServerConfig", k, v)
	return m.NextErr()
}
