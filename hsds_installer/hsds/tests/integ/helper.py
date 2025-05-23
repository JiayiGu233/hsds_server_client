##############################################################################
# Copyright by The HDF Group.                                                #
# All rights reserved.                                                       #
#                                                                            #
# This file is part of HSDS (HDF5 Scalable Data Service), Libraries and      #
# Utilities.  The full HSDS copyright notice, including                      #
# terms governing use, modification, and redistribution, is contained in     #
# the file COPYING, which can be found at the root of the source code        #
# distribution tree.  If you do not have access to this file, you may        #
# request a copy from help@hdfgroup.org.                                     #
##############################################################################
import requests
import requests_unixsocket
import json
import os.path as op
import random
import string
import base64

import config


def getEndpoint():
    """Get endpoint we'll send HTTP requests to"""
    endpoint = config.get("hsds_endpoint")
    return endpoint


def getSession():
    """Get session object"""
    endpoint = getEndpoint()

    if endpoint.endswith(".sock"):
        # use requests_unixsocket to get a socket session
        # Expect endpoint in the form:
        #     http+unix://%2Ftmp%2Fsn_1.sock
        session = requests_unixsocket.Session()
    else:
        session = requests.Session()
    return session


def getRangeGetEndpoint():
    """Get endpoint we'll send HTTP range GET requests to"""
    endpoint = config.get("rangeget_endpoint")
    return endpoint


def validateId(id):
    """Return true if the parameter looks like a UUID"""
    if not isinstance(id, str):
        # should be a string
        return False
    if len(id) != 38:
        # id's returned by uuid.uuid1() are always 38 chars long
        return False
    return True


def getActiveNodeCount(session=None):
    """Return number of active sn/dn nodes"""
    req = getEndpoint("head") + "/info"
    rsp = session.get(req)
    rsp_json = json.loads(rsp.text)
    sn_count = rsp_json["active_sn_count"]
    dn_count = rsp_json["active_dn_count"]
    return sn_count, dn_count


def getTestDomainName(name):
    """Get base domain to use for test_cases"""
    domain = "/home/"
    domain += config.get('user_name')
    domain += '/'
    domain += 'hsds_test'
    domain += '/'
    domain += name.lower()
    domain += '/'
    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    domain += random_str
    return domain


def getRandomName():
    """Return a random name"""
    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return random_str


def getRequestHeaders(domain=None, username=None, bucket=None, password=None, **kwargs):
    """Get default request headers for domain"""
    if username is None:
        username = config.get("user_name")
        if password is None:
            password = config.get("user_password")
    elif password is None and username == config.get("user2_name"):
        if password is None:
            password = config.get("user2_password")
    headers = dict()
    if domain is not None:
        # if config.get("bucket_name"):
        #    domain = config.get("bucket_name") + domain
        headers['X-Hdf-domain'] = domain.encode('utf-8')
    if username and password:
        auth_string = username + ':' + password
        auth_string = auth_string.encode('utf-8')
        auth_string = base64.b64encode(auth_string)
        auth_string = b"Basic " + auth_string
        headers['Authorization'] = auth_string

    if config.get("bucket_name"):
        bucket_name = config.get("bucket_name")
    else:
        bucket_name = bucket
    if bucket_name:
        headers['X-Hdf-bucket'] = bucket_name.encode('utf-8')

    for k in kwargs.keys():
        headers[k] = kwargs[k]
    return headers


def getParentDomain(domain):
    """Get parent domain of given domain."""
    parent = op.dirname(domain)
    if not parent:
        raise ValueError("Invalid domain")  # can't end with dot
    return parent


def setupDomain(domain, folder=False, username=None, password=None, root_gcpl=None):
    """Create domain (and parent domain if needed)"""
    endpoint = config.get("hsds_endpoint")
    headers = getRequestHeaders(domain=domain, username=username, password=password)
    req = endpoint + "/"
    with getSession() as session:
        rsp = session.get(req, headers=headers)
        if rsp.status_code == 200:
            return  # already have domain
        if rsp.status_code not in (404, 410):
            # something other than "not found"
            raise ValueError(f"Unexpected get domain error: {rsp.status_code}")
        parent_domain = getParentDomain(domain)
        if parent_domain is None:
            raise ValueError(f"Invalid parent domain: {domain}")
        # create parent domain if needed
        setupDomain(parent_domain, folder=True)

        headers = getRequestHeaders(domain=domain)

        body = {}
        if folder:
            body["folder"] = True
        if root_gcpl is not None:
            body["group"] = {"creationProperties": root_gcpl}

        if body != {}:
            rsp = session.put(req, data=json.dumps(body), headers=headers)
        else:
            rsp = session.put(req, headers=headers)
        if rsp.status_code != 201:
            raise ValueError(f"Unexpected put domain error: {rsp.status_code}")


def getRootUUID(domain, username=None, password=None, session=None):
    """Get root uuid for domain"""
    req = getEndpoint() + "/"
    headers = getRequestHeaders(domain=domain, username=username, password=password)

    rsp = session.get(req, headers=headers)
    root_uuid = None
    if rsp.status_code == 200:
        rspJson = json.loads(rsp.text)
        root_uuid = rspJson["root"]
    return root_uuid


def getTestDomain(name):
    """Get a domain for one of the test files"""
    username = config.get("user_name")
    path = f'/home/{username}/test/{name}'
    return path


def getUUIDByPath(domain, path, username=None, password=None, session=None):
    """Get uuid for a given path"""
    if path[0] != '/':
        raise KeyError("only abs paths")  # only abs paths

    parent_uuid = getRootUUID(domain, username=username, password=password, session=session)

    if path == '/':
        return parent_uuid

    headers = getRequestHeaders(domain=domain)

    # make a fake tgt_json to represent 'link' to root group
    tgt_json = {
        'collection': "groups",
        'class': "H5L_TYPE_HARD",
        'id': parent_uuid
    }
    tgt_uuid = None

    names = path.split('/')

    for name in names:
        if not name:
            continue
        if parent_uuid is None:
            raise KeyError("not found")

        req = getEndpoint() + "/groups/" + parent_uuid + "/links/" + name
        rsp = session.get(req, headers=headers)
        if rsp.status_code != 200:
            raise KeyError("not found")
        rsp_json = json.loads(rsp.text)
        tgt_json = rsp_json['link']

        if tgt_json['class'] == 'H5L_TYPE_HARD':
            if tgt_json['collection'] == 'groups':
                parent_uuid = tgt_json['id']
            else:
                parent_uuid = None
            tgt_uuid = tgt_json['id']
        else:
            raise KeyError("non-hard link")
    return tgt_uuid


def getHDF5JSON(filename):
    """Get HDF5 JSON dump for chunk locations"""
    if not op.isfile(filename):
        return None
    hdf5_json = None
    with open(filename) as f:
        hdf5_json = json.load(f)
    return hdf5_json


def getLink(domain, grp_id, title):
    headers = getRequestHeaders(domain=domain)
    session = getSession()
    req = getEndpoint() + "/groups/" + grp_id + "/links/" + title
    rsp = session.get(req, headers=headers)
    if rsp.status_code in (404, 410):
        # not found or deleted
        return None
    elif rsp.status_code != 200:
        raise ValueError(f"getLink exception: {rsp.status_code}")

    rspJson = json.loads(rsp.text)
    if "link" not in rspJson:
        raise KeyError(f"expected link key in {rspJson}")
    link_json = rspJson["link"]

    session.close()

    return link_json
