// Copyright 2015 Canonical Ltd.
// Licensed under the AGPLv3, see LICENCE file for details.

package state_test

import (
	"github.com/juju/errors"
	jc "github.com/juju/testing/checkers"
	gc "gopkg.in/check.v1"
	"gopkg.in/juju/charm.v6-unstable"
	"gopkg.in/juju/names.v2"

	"github.com/juju/juju/core/crossmodel"
	"github.com/juju/juju/permission"
	"github.com/juju/juju/state"
	"github.com/juju/juju/testing/factory"
)

type applicationOffersSuite struct {
	ConnSuite
}

var _ = gc.Suite(&applicationOffersSuite{})

func (s *applicationOffersSuite) SetUpTest(c *gc.C) {
	s.ConnSuite.SetUpTest(c)
	ch := s.AddTestingCharm(c, "mysql")
	s.AddTestingService(c, "mysql", ch)
}

func (s *applicationOffersSuite) createDefaultOffer(c *gc.C) crossmodel.ApplicationOffer {
	eps := map[string]string{"db": "server", "db-admin": "server-admin"}
	sd := state.NewApplicationOffers(s.State)
	owner := s.Factory.MakeUser(c, nil)
	offerArgs := crossmodel.AddApplicationOfferArgs{
		OfferName:              "hosted-mysql",
		ApplicationName:        "mysql",
		ApplicationDescription: "mysql is a db server",
		Endpoints:              eps,
		Owner:                  owner.Name(),
	}
	offer, err := sd.AddOffer(offerArgs)
	c.Assert(err, jc.ErrorIsNil)
	return *offer
}

func (s *applicationOffersSuite) TestEndpoints(c *gc.C) {
	offer := s.createDefaultOffer(c)
	_, err := state.ApplicationOfferEndpoint(offer, "foo")
	c.Assert(err, gc.ErrorMatches, `relation "foo" on application offer "mysql" not found`)

	serverEP, err := state.ApplicationOfferEndpoint(offer, "server")
	c.Assert(err, jc.ErrorIsNil)
	c.Assert(serverEP, gc.DeepEquals, state.Endpoint{
		ApplicationName: "mysql",
		Relation: charm.Relation{
			Interface: "mysql",
			Name:      "server",
			Role:      charm.RoleProvider,
			Scope:     charm.ScopeGlobal,
		},
	})
}

func (s *applicationOffersSuite) TestRemove(c *gc.C) {
	offer := s.createDefaultOffer(c)
	sd := state.NewApplicationOffers(s.State)
	err := sd.Remove(offer.OfferName)
	c.Assert(err, jc.ErrorIsNil)
	_, err = state.OfferForName(sd, offer.OfferName)
	c.Assert(err, jc.Satisfies, errors.IsNotFound)
}

func (s *applicationOffersSuite) TestAddApplicationOffer(c *gc.C) {
	eps := map[string]string{"db": "server", "db-admin": "server-admin"}
	sd := state.NewApplicationOffers(s.State)
	owner := s.Factory.MakeUser(c, nil)
	args := crossmodel.AddApplicationOfferArgs{
		OfferName:              "hosted-mysql",
		ApplicationName:        "mysql",
		ApplicationDescription: "mysql is a db server",
		Endpoints:              eps,
		Owner:                  owner.Name(),
		HasRead:                []string{"everyone@external"},
	}
	offer, err := sd.AddOffer(args)
	c.Assert(err, jc.ErrorIsNil)
	doc, err := state.OfferForName(sd, "hosted-mysql")
	c.Assert(err, jc.ErrorIsNil)
	expectedOffer, err := state.MakeApplicationOffer(sd, doc)
	c.Assert(*offer, jc.DeepEquals, *expectedOffer)

	offerTag := names.NewApplicationOfferTag(offer.OfferName)
	access, err := s.State.GetOfferAccess(offerTag, owner.UserTag())
	c.Assert(err, jc.ErrorIsNil)
	c.Assert(access, gc.Equals, permission.AdminAccess)

	access, err = s.State.GetOfferAccess(offerTag, names.NewUserTag("everyone@external"))
	c.Assert(err, jc.ErrorIsNil)
	c.Assert(access, gc.Equals, permission.ReadAccess)
}

func (s *applicationOffersSuite) TestAddApplicationOfferBadEndpoints(c *gc.C) {
	eps := map[string]string{"db": "server", "db-admin": "admin"}
	sd := state.NewApplicationOffers(s.State)
	owner := s.Factory.MakeUser(c, nil)
	args := crossmodel.AddApplicationOfferArgs{
		OfferName:              "hosted-mysql",
		ApplicationName:        "mysql",
		ApplicationDescription: "mysql is a db server",
		Endpoints:              eps,
		Owner:                  owner.Name(),
	}
	_, err := sd.AddOffer(args)
	c.Assert(err, gc.ErrorMatches, `.*application "mysql" has no "admin" relation`)

	// Fix the endpoints and try again.
	// There was a bug where this failed so we test it.
	eps = map[string]string{"db": "server", "db-admin": "server-admin"}
	args.Endpoints = eps
	_, err = sd.AddOffer(args)
	c.Assert(err, jc.ErrorIsNil)
}

func (s *applicationOffersSuite) TestListOffersNone(c *gc.C) {
	sd := state.NewApplicationOffers(s.State)
	offers, err := sd.ListOffers()
	c.Assert(err, jc.ErrorIsNil)
	c.Assert(len(offers), gc.Equals, 0)
}

func (s *applicationOffersSuite) createOffer(c *gc.C, name, description string) crossmodel.ApplicationOffer {
	eps := map[string]string{
		"db": "server",
	}
	sd := state.NewApplicationOffers(s.State)
	owner := s.Factory.MakeUser(c, nil)
	offerArgs := crossmodel.AddApplicationOfferArgs{
		OfferName:              name,
		ApplicationName:        "mysql",
		ApplicationDescription: description,
		Endpoints:              eps,
		Owner:                  owner.Name(),
	}
	offer, err := sd.AddOffer(offerArgs)
	c.Assert(err, jc.ErrorIsNil)
	return *offer
}

func (s *applicationOffersSuite) TestApplicationOffer(c *gc.C) {
	sd := state.NewApplicationOffers(s.State)
	expectedOffer := s.createDefaultOffer(c)
	offer, err := sd.ApplicationOffer("hosted-mysql")
	c.Assert(err, jc.ErrorIsNil)
	c.Assert(*offer, jc.DeepEquals, expectedOffer)
}

func (s *applicationOffersSuite) TestListOffersAll(c *gc.C) {
	sd := state.NewApplicationOffers(s.State)
	offer := s.createDefaultOffer(c)
	offers, err := sd.ListOffers()
	c.Assert(err, jc.ErrorIsNil)
	c.Assert(len(offers), gc.Equals, 1)
	c.Assert(offers[0], jc.DeepEquals, offer)
}

func (s *applicationOffersSuite) TestListOffersOneFilter(c *gc.C) {
	sd := state.NewApplicationOffers(s.State)
	offer := s.createOffer(c, "offer1", "description for offer1")
	s.createOffer(c, "offer2", "description for offer2")
	s.createOffer(c, "offer3", "description for offer3")
	offers, err := sd.ListOffers(crossmodel.ApplicationOfferFilter{
		OfferName:       "offer1",
		ApplicationName: "mysql",
	})
	c.Assert(err, jc.ErrorIsNil)
	c.Assert(len(offers), gc.Equals, 1)
	c.Assert(offers[0], jc.DeepEquals, offer)
}

func (s *applicationOffersSuite) TestListOffersManyFilters(c *gc.C) {
	sd := state.NewApplicationOffers(s.State)
	offer := s.createOffer(c, "offer1", "description for offer1")
	offer2 := s.createOffer(c, "offer2", "description for offer2")
	s.createOffer(c, "offer3", "description for offer3")
	offers, err := sd.ListOffers(
		crossmodel.ApplicationOfferFilter{
			OfferName:       "offer1",
			ApplicationName: "mysql",
		},
		crossmodel.ApplicationOfferFilter{
			OfferName:              "offer2",
			ApplicationDescription: "offer2",
		},
	)
	c.Assert(err, jc.ErrorIsNil)
	c.Assert(len(offers), gc.Equals, 2)
	c.Assert(offers, jc.DeepEquals, []crossmodel.ApplicationOffer{offer, offer2})
}

func (s *applicationOffersSuite) TestListOffersFilterDescriptionRegexp(c *gc.C) {
	sd := state.NewApplicationOffers(s.State)
	s.createOffer(c, "offer1", "description for offer1")
	offer := s.createOffer(c, "offer2", "description for offer2")
	s.createOffer(c, "offer3", "description for offer3")
	offers, err := sd.ListOffers(crossmodel.ApplicationOfferFilter{
		ApplicationDescription: "for offer2",
	})
	c.Assert(err, jc.ErrorIsNil)
	c.Assert(len(offers), gc.Equals, 1)
	c.Assert(offers[0], jc.DeepEquals, offer)
}

func (s *applicationOffersSuite) TestListOffersFilterOfferNameRegexp(c *gc.C) {
	sd := state.NewApplicationOffers(s.State)
	offer := s.createOffer(c, "hosted-offer1", "description for offer1")
	s.createOffer(c, "offer2", "description for offer2")
	s.createOffer(c, "offer3", "description for offer3")
	offers, err := sd.ListOffers(crossmodel.ApplicationOfferFilter{
		OfferName: "offer1",
	})
	c.Assert(err, jc.ErrorIsNil)
	c.Assert(len(offers), gc.Equals, 1)
	c.Assert(offers[0], jc.DeepEquals, offer)
}

func (s *applicationOffersSuite) TestAddApplicationOfferDuplicate(c *gc.C) {
	sd := state.NewApplicationOffers(s.State)
	owner := s.Factory.MakeUser(c, nil)
	_, err := sd.AddOffer(crossmodel.AddApplicationOfferArgs{
		OfferName:       "hosted-mysql",
		ApplicationName: "mysql",
		Owner:           owner.Name(),
	})
	c.Assert(err, jc.ErrorIsNil)
	_, err = sd.AddOffer(crossmodel.AddApplicationOfferArgs{
		OfferName:       "hosted-mysql",
		ApplicationName: "mysql",
		Owner:           owner.Name(),
	})
	c.Assert(err, gc.ErrorMatches, `cannot add application offer "hosted-mysql": application offer already exists`)
}

func (s *applicationOffersSuite) TestAddApplicationOfferDuplicateAddedAfterInitial(c *gc.C) {
	// Check that a record with a URL conflict cannot be added if
	// there is no conflict initially but a record is added
	// before the transaction is run.
	sd := state.NewApplicationOffers(s.State)
	owner := s.Factory.MakeUser(c, nil)
	defer state.SetBeforeHooks(c, s.State, func() {
		_, err := sd.AddOffer(crossmodel.AddApplicationOfferArgs{
			OfferName:       "hosted-mysql",
			ApplicationName: "mysql",
			Owner:           owner.Name(),
		})
		c.Assert(err, jc.ErrorIsNil)
	}).Check()
	_, err := sd.AddOffer(crossmodel.AddApplicationOfferArgs{
		OfferName:       "hosted-mysql",
		ApplicationName: "mysql",
		Owner:           owner.Name(),
	})
	c.Assert(err, gc.ErrorMatches, `cannot add application offer "hosted-mysql": application offer already exists`)
}

func (s *applicationOffersSuite) TestUpdateApplicationOffer(c *gc.C) {
	sd := state.NewApplicationOffers(s.State)
	owner := s.Factory.MakeUser(c, nil)
	_, err := sd.AddOffer(crossmodel.AddApplicationOfferArgs{
		OfferName:       "hosted-mysql",
		ApplicationName: "mysql",
		Owner:           owner.Name(),
	})
	c.Assert(err, jc.ErrorIsNil)
	s.Factory.MakeApplication(c, &factory.ApplicationParams{Name: "foo"})
	offer, err := sd.UpdateOffer(crossmodel.AddApplicationOfferArgs{
		OfferName:       "hosted-mysql",
		ApplicationName: "foo",
		Owner:           owner.Name(),
	})
	c.Assert(err, jc.ErrorIsNil)
	c.Assert(offer, jc.DeepEquals, &crossmodel.ApplicationOffer{
		OfferName:       "hosted-mysql",
		ApplicationName: "foo",
		Endpoints:       map[string]charm.Relation{},
	})
}

func (s *applicationOffersSuite) TestUpdateApplicationOfferNotFound(c *gc.C) {
	sd := state.NewApplicationOffers(s.State)
	owner := s.Factory.MakeUser(c, nil)
	_, err := sd.UpdateOffer(crossmodel.AddApplicationOfferArgs{
		OfferName:       "hosted-mysql",
		ApplicationName: "foo",
		Owner:           owner.Name(),
	})
	c.Assert(err, gc.ErrorMatches, `cannot update application offer "foo": application offer "hosted-mysql" not found`)
}

func (s *applicationOffersSuite) TestUpdateApplicationOfferRemovedAfterInitial(c *gc.C) {
	// Check that a record with a URL conflict cannot be added if
	// there is no conflict initially but a record is added
	// before the transaction is run.
	sd := state.NewApplicationOffers(s.State)
	owner := s.Factory.MakeUser(c, nil)
	_, err := sd.AddOffer(crossmodel.AddApplicationOfferArgs{
		OfferName:       "hosted-mysql",
		ApplicationName: "mysql",
		Owner:           owner.Name(),
	})
	c.Assert(err, jc.ErrorIsNil)
	defer state.SetBeforeHooks(c, s.State, func() {
		err := sd.Remove("hosted-mysql")
		c.Assert(err, jc.ErrorIsNil)
	}).Check()
	_, err = sd.UpdateOffer(crossmodel.AddApplicationOfferArgs{
		OfferName:       "hosted-mysql",
		ApplicationName: "mysql",
		Owner:           owner.Name(),
	})
	c.Assert(err, gc.ErrorMatches, `cannot update application offer "mysql": application offer "hosted-mysql" not found`)
}
