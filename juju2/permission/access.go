// Copyright 2016 Canonical Ltd.
// Licensed under the AGPLv3, see LICENCE file for details.

package permission

import (
	"github.com/juju/errors"
	"github.com/juju/schema"
)

// Access represents a level of access.
type Access string

const (
	// NoAccess allows a user no permissions at all.
	NoAccess Access = ""

	// Model Permissions

	// ReadAccess allows a user to read information about a permission subject,
	// without being able to make any changes.
	ReadAccess Access = "read"

	// WriteAccess allows a user to make changes to a permission subject.
	WriteAccess Access = "write"

	// AdminAccess allows a user full control over the subject.
	AdminAccess Access = "admin"

	// Controller permissions

	// LoginAccess allows a user to log-ing into the subject.
	LoginAccess Access = "login"

	// AddModelAccess allows user to add new models in subjects supporting it.
	AddModelAccess Access = "add-model"

	// SuperuserAccess allows user unrestricted permissions in the subject.
	SuperuserAccess Access = "superuser"
)

// Validate returns error if the current is not a valid access level.
func (a Access) Validate() error {
	switch a {
	case NoAccess, AdminAccess, ReadAccess, WriteAccess,
		LoginAccess, AddModelAccess, SuperuserAccess:
		return nil
	}
	return errors.NotValidf("access level %s", a)
}

// ValidateModelAccess returns error if the passed access is not a valid
// model access level.
func ValidateModelAccess(access Access) error {
	switch access {
	case ReadAccess, WriteAccess, AdminAccess:
		return nil
	}
	return errors.NotValidf("%q model access", access)
}

//ValidateControllerAccess returns error if the passed access is not a valid
// controller access level.
func ValidateControllerAccess(access Access) error {
	switch access {
	case LoginAccess, AddModelAccess, SuperuserAccess:
		return nil
	}
	return errors.NotValidf("%q controller access", access)
}

func (a Access) controllerValue() int {
	switch a {
	case NoAccess:
		return 0
	case LoginAccess:
		return 1
	case AddModelAccess:
		return 2
	case SuperuserAccess:
		return 3
	default:
		return -1
	}
}

func (a Access) modelValue() int {
	switch a {
	case NoAccess:
		return 0
	case ReadAccess:
		return 1
	case WriteAccess:
		return 2
	case AdminAccess:
		return 3
	default:
		return -1
	}
}

// EqualOrGreaterModelAccessThan returns true if the current access is equal
// or greater than the passed in access level.
func (a Access) EqualOrGreaterModelAccessThan(access Access) bool {
	v1, v2 := a.modelValue(), access.modelValue()
	if v1 < 0 || v2 < 0 {
		return false
	}
	return v1 >= v2
}

// GreaterModelAccessThan returns true if the current access is greater than
// the passed in access level.
func (a Access) GreaterModelAccessThan(access Access) bool {
	v1, v2 := a.modelValue(), access.modelValue()
	if v1 < 0 || v2 < 0 {
		return false
	}
	return v1 > v2
}

// EqualOrGreaterControllerAccessThan returns true if the current access is
// equal or greater than the passed in access level.
func (a Access) EqualOrGreaterControllerAccessThan(access Access) bool {
	v1, v2 := a.controllerValue(), access.controllerValue()
	if v1 < 0 || v2 < 0 {
		return false
	}
	return v1 >= v2
}

// GreaterControllerAccessThan returns true if the current access is
// greater than the passed in access level.
func (a Access) GreaterControllerAccessThan(access Access) bool {
	v1, v2 := a.controllerValue(), access.controllerValue()
	if v1 < 0 || v2 < 0 {
		return false
	}
	return v1 > v2
}

// accessField returns a Checker that accepts a string value only
// and returns a valid Access or an error.
func accessField() schema.Checker {
	return accessC{}
}

type accessC struct{}

func (c accessC) Coerce(v interface{}, path []string) (interface{}, error) {
	s := schema.String()
	in, err := s.Coerce(v, path)
	if err != nil {
		return nil, err
	}
	access := Access(in.(string))
	if err := access.Validate(); err != nil {
		return nil, errors.Trace(err)
	}
	return access, nil
}
