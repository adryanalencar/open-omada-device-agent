# Security Policy

## Project status

Open Omada Device Agent is experimental interoperability software. It opens
network connections to an Omada controller and intentionally implements a
subset of a device-management protocol. Treat it as lab software unless you
have reviewed the code and deployment model for your environment.

## Sensitive material

Do not commit or publish:

- Device Account passwords;
- controller/cloud authentication tokens or cookies;
- private keys or client certificates;
- `.env` files;
- packet captures from networks you are not authorized to inspect;
- managed-state files containing sensitive deployment metadata.

The agent's managed-state file is designed not to persist the Device Account
password, but it still contains controller identifiers and routing metadata and
should be treated as operational data.

## TLS

Certificate verification is disabled by default because Omada management
endpoints commonly use private or self-signed certificates. This protects
interoperability but does not authenticate the controller certificate.

For environments with a trusted certificate chain, set:

```dotenv
OMADA_TLS_VERIFY=true
OMADA_TLS_CA_FILE=/path/to/ca.pem
```

## Reporting vulnerabilities

Please use GitHub's private vulnerability reporting feature for the repository
when available. Do not open a public issue containing credentials, exploit
material against third-party systems, or private packet captures.
