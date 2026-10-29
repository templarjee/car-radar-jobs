"""Bounded public source reads with robots checks; no probe or hard-coded targets."""
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser
AGENT="CarRadarPublicAggregateRefresh/1.0 (robots-respecting, bounded)"

def read_limited(url:str,limit:int=900000)->tuple[int,bytes,str]:
    request=Request(url,headers={"User-Agent":AGENT,"Accept":"text/html,text/plain;q=0.9"},
                    method="GET")
    with urlopen(request,timeout=15) as response:
        if urlparse(response.url).hostname!=urlparse(url).hostname:
            raise ValueError("Cross-host redirect refused")
        encoded=response.read(limit+1)
        if len(encoded)>limit:
            raise ValueError("Source exceeds byte limit")
        return response.status,encoded,response.headers.get_content_charset() or "utf-8"


def robots_allows(url:str)->tuple[bool,str]:
    parsed=urlparse(url)
    robots=f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        status,data,charset=read_limited(robots,150000)
        if status!=200:return False,"robots_not_200"
        raw=data.decode(charset,errors="replace")
        parser=RobotFileParser()
        parser.parse(raw.splitlines())
        if not parser.can_fetch(AGENT,url):
            return False,"robots_disallows"
        return True,"robots_allows"
    except HTTPError as err:
        return False,f"robots_http_{err.code}_not_confirmed"
    except (URLError,TimeoutError,ValueError) as err:
        return False,f"robots_unavailable_{type(err).__name__}"

