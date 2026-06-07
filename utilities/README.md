# check_and_append_cacert.py
This utility patches the cacert 'slug' from certifi with the ca.crt provided

To allow secure communication with HashiCorp's Vault (and the Kubernetes API), the Certificate Auythority's public cert must be available.  If you're using 'real' certs from a 'well-known' source, this is completely unnecessary.  If however, you are using self-signed certs this is a must.