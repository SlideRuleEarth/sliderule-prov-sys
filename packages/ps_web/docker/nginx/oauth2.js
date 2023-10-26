/*
 * This function is called by the NGINX auth_request directive to perform OAuth 2.0
 * Token Introspection. It uses a subrequest to construct a Token Introspection request
 * to the configured authorization server ($oauth_token_endpoint).
 *
 * Responses are aligned with the valid responses for auth_request:
 * 204: token is active
 * 403: token is not active
 * 401: error condition (details written to error log at error level)
 * 
 * Metadata contained within the token introspection JSON response is converted to response
 * headers. These in turn are available to the auth_request location with the auth_request_set
 * directive. Each member of the response is available to nginx as $sent_http_oauth_<member name>
 *
 * Copyright (C) 2019 Nginx, Inc.
 */
import qs from "querystring";
function introspectAccessToken(r) {
    // Prepare Authorization header for the introspection request
    var authHeader = "";
    //We will do a stricter implementaton and put the token in the Authorization header
    // if (r.variables.oauth_client_id.length) {
    //     var basicAuthPlaintext = r.variables.oauth_client_id + ":" + r.variables.oauth_client_secret;
    //     authHeader = "Basic " + basicAuthPlaintext.toBytes().toString('base64');    
    //     r.log(basicAuthPlaintext)
    // } else {
    //     authHeader = "Bearer " + r.variables.oauth_client_secret;
    // }
    let args = qs.parse(r.variables.original_uri.split('?')[1]);
    r.log("args.name:"+args.name);
    r.log("$original_uri:"+r.variables.original_uri);
    // Make the OAuth 2.0 Token Introspection request
    r.log("OAuth sending introspection request with token: " + r.variables.access_token)
    authHeader = "Bearer " + r.variables.access_token
    r.subrequest("/_oauth2_send_introspection_request", "token=" + r.variables.access_token + "&authorization=" + authHeader,
        function(reply) {
            if (reply.status != 200) {
                r.error("OAuth unexpected response from authorization server (HTTP " + reply.status + "). " + reply.body);
                r.return(401);
            }

            // We have a response from authorization server, validate it has expected JSON schema
            try {
                r.log("OAuth token introspection response: " + reply.responseBody)
                var response = JSON.parse(reply.responseBody);
                // TODO: check for errors in the JSON response first
                // We have a valid introspection response
                // Check for validation success
                if (response.active == true) {
                    r.warn("OAuth token introspection found ACTIVE token");
                    // Iterate over all members of the response and return them as response headers
                    for (var p in response) {
                        if (!response.hasOwnProperty(p)) continue;
                        r.log("OAuth token value " + p + ": " + response[p]);
                        r.headersOut['token-' + p] = response[p];
                    }
                    r.status = 204;
                    r.sendHeader();
                    r.finish();
                } else {
                    r.warn("OAuth token introspection found inactive token");
                    r.return(403);
                }
            } catch (e) {
                r.error("OAuth token introspection response is not JSON: " + reply.body);
                r.return(401);
            }
        }
    );
    r.return(401);
}

export default { introspectAccessToken }

//export default { introspectAccessToken }