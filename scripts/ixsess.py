import hashlib, re, sys, urllib.request, http.cookiejar

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
opener.addheaders = [("User-Agent","Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"),("Accept","*/*")]

def raw(url):
    try:
        with opener.open(url, timeout=60) as r:
            return r.status, dict(r.headers), r.read().decode("utf-8","replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8","replace")

def solve_from(body):
    m = re.search(r"DIFFICULTY_BITS\s*=\s*(\d+).*?nonce\s*=\s*\"([0-9a-f]+)\".*?TS\s*=\s*\"(\d+)\"", body, re.S)
    if not m: return False
    bits, nonce, ts = int(m.group(1)), m.group(2), m.group(3)
    i = 0
    while True:
        h = hashlib.sha256((nonce+str(i)).encode()).digest()
        v = (h[0]<<16)|(h[1]<<8)|h[2]
        if (24 - v.bit_length() if v else 24) >= bits: break
        i += 1
    import http.cookiejar as cj
    c = cj.Cookie(0,"pow_token",f"{nonce}:{ts}:{i}",None,False,"ixtheo.de",False,False,"/",True,True,None,False,None,None,{})
    jar.set_cookie(c)
    print(f"[pow solved i={i}]", file=sys.stderr)
    return True

def get(url, tries=3):
    for _ in range(tries):
        st, hd, body = raw(url)
        if "DIFFICULTY_BITS" in body and "Verifying your browser" in body:
            solve_from(body); continue
        return st, hd, body
    return st, hd, body

if __name__ == "__main__":
    for url in sys.argv[1:]:
        st, hd, body = get(url)
        print("=====", url)
        print("STATUS", st, "CT", hd.get("Content-Type"))
        print(body[:4000])
        print()
