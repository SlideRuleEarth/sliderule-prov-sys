"""Tests for sliderule-python icesat2 api."""

import pytest
import sliderule


@pytest.mark.system
def test_authenticate(setup_logging, domain, organization):
    logger = setup_logging
    sliderule.set_url(domain)
    status = sliderule.authenticate(organization)
    assert status

@pytest.mark.system
def test_num_nodes_update(setup_logging, domain, organization):
    logger = setup_logging
    sliderule.set_url(domain)
    status = sliderule.authenticate(organization)
    assert status
    result = sliderule.update_available_servers(7,20)
    assert len(result) == 2
    assert type(result[0]) == int
    assert type(result[1]) == int

@pytest.mark.system
def test_bad_org(setup_logging, domain):
    logger = setup_logging
    sliderule.set_url(domain)
    status = sliderule.authenticate("non_existent_org")
    assert status == False

@pytest.mark.system
def test_bad_creds(setup_logging, domain, organization):
    logger = setup_logging
    sliderule.set_url(domain)
    status = sliderule.authenticate(organization, "missing_user", "wrong_password")
    assert status == False


@pytest.mark.system
@pytest.mark.parametrize(
'domain, organization, desired_nodes',
[
    ('testsliderule.org','UofMDTest',1),
    ('testsliderule.org','UofMDTest',2),
])
def test_provisioning(setup_logging, domain, organization, desired_nodes):
    logger = setup_logging
    sliderule.init(domain, organization=organization, desired_nodes=desired_nodes, time_to_live=15)
    v = sliderule.get_version()
    logger.info(f"version:{v}")
    assert v['organization'] == organization

@pytest.mark.system
@pytest.mark.parametrize(
'domain, organization',
[
    ('testsliderule.org','UofMDTest'),
])
def test_authenticate_p(setup_logging, domain, organization):
    logger = setup_logging
    sliderule.set_url(domain)
    status = sliderule.authenticate(organization)
    logger.info(f"status:{status}")
    assert status

@pytest.mark.system
@pytest.mark.parametrize(
'domain, organization',
[
    ('testsliderule.org','UofMDTest'),
])
def test_num_nodes_update_p(setup_logging, domain, organization):
    logger = setup_logging
    sliderule.set_url(domain)
    status = sliderule.authenticate(organization)
    assert status
    num_servers,max_workers = sliderule.update_available_servers(desired_nodes=1,time_to_live=15)
    logger.critical(f"num_servers:{num_servers} max_workers:{max_workers}")
    assert type(num_servers) == int
    assert type(max_workers) == int