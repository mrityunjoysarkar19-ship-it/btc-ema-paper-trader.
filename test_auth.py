from exchange.authentication import sign_request
def test_signature():
    s=sign_request("secret","GET","123","/v2/orders","?product_id=1&state=open","")
    assert len(s)==64 and s==sign_request("secret","GET","123","/v2/orders","?product_id=1&state=open","")
