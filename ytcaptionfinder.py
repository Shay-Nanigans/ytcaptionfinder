from datetime import datetime
from multiprocessing import Pool
import sys
import yt_dlp
import os
import json
import re
import tblib.pickling_support
tblib.pickling_support.install()

#wrapper for when one of the threads does a die
class ExceptionWrapper(object):
    def __init__(self, ee):
        self.ee = ee
        __, __, self.tb = sys.exc_info()
    def re_raise(self):
        raise self.ee.with_traceback(self.tb)

def getIdList(url):
    ydl_opts = {
            'dump_single_json':True,
            'extract_flat':True,
            'skip_download':True,
        }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as yt:
            result = yt.extract_info( url,False)
    except Exception as e:
        print(e)
        return []
    if 'entries' in result:
        results = []
        for item in result['entries']:
            results.append(item['id'])
        return results
    else:
        return [result['id']]



#takes a id and a string and downloads all the captions and returns a list of youtube links with the 
def toUrls(times, endtime:bool=False):
    urls = []
    if endtime:
        for url in times:
            urls.append(f"https://youtu.be/{url[0]} {url[1]} {url[2]}")
    else:
        for url in times:
            urls.append(f"https://youtu.be/{url[0]}?t={int(url[1])}")
    return urls

def findPhraseTime(args):
    '''args = [id, searchstring, usedids]'''
    id, searchstring, usedids =args
    try:
        #compiles the regex pattern to search
        searchstring = re.compile(rf"{searchstring}", re.IGNORECASE)

        ydl_opts = {
                    'outtmpl': f"{os.getcwd()}/temp/%(id)s.%(ext)s", 
                    # 'download_archive':f"{os.getcwd()}/temp/dl.txt",
                    'writesubtitles': True, 
                    'writeautomaticsub': True, 
                    'subtitlesformat':"json3",
                    'skip_download':True,
                    'nooverwrites':True

                }

        if f"{id}\n" not in usedids:
            yt = yt_dlp.YoutubeDL(ydl_opts)
            yt.download(id)
            open('temp/ids.txt','a').write(f'{id}\n')

        matches = []

        #searches everything it just downloaded for the string
        for file in os.listdir(f"temp/"):
            if ".json3" not in file: continue
            if id not in file: continue
            print(file)
            with open(f"temp/{file}","r",encoding="utf8", errors='ignore') as f: #open the file
                total = 0
                lines = []
                j = json.load(f)
                charcount = 0
                script = "" #a string of the ENTIRE videos captions

                #each file is a list of events made up a list of segments
                #i should probably put lines,script into a file for future searches?
                for event in j["events"]:
                    total = total + 1
                    if "segs" in event:
                        for seg in event["segs"]:
                            if seg["utf8"] != "\n": #newline is cursed for autocaptioned video
                                thisline = re.sub(r'[^A-Za-z0-9 ]+', '', seg["utf8"]).strip().replace("  ", " ") + " "
                                if "tOffsetMs" in seg:#builds a list of charactercount, timestamp pairs for all the segments
                                    lines.append([charcount,(float(event["tStartMs"]/1000) + float(seg["tOffsetMs"]/1000))]) 
                                else:    
                                    lines.append([charcount,float(event["tStartMs"]/1000)]) 
                                charcount = charcount + len(thisline)
                                script = script + thisline
                
                #finds all the matches and when in the video it happens
                for m in re.finditer(searchstring,script):
                    print(m)
                    startplace = 0
                    while(m.start()>lines[startplace][0]):
                        startplace = startplace + 1
                        if len(lines) == startplace:
                            break

                    endplace = 0
                    while(m.end()>lines[endplace][0]):
                        endplace = endplace + 1
                        if len(lines) == endplace:
                            break

                    if len(lines) > endplace:
                        if startplace == 0:
                            matches.append([id, lines[startplace][1],lines[endplace][1]])
                            # matches.append(f"https://youtu.be/{id}?t={lines[lineplace][1]}")
                        else:
                            matches.append([id, lines[startplace-1][1],lines[endplace][1]])
                            # matches.append(f"https://youtu.be/{id}?t={lines[lineplace-1][1]}")
        return matches
    except Exception as e:
        return ExceptionWrapper(e)


def findList(searchstring:str, urls:list):
    #make folders
    if not os.path.exists(f"temp/"): os.makedirs(f"temp/")
    if not os.path.exists(f"temp/ids.txt"): open(f"temp/ids.txt", 'w'). close()
    newurls = []
    for url in urls:
        for item in cleanInput(url):
            newurls.append(item)
    urls = newurls
    #id fetching
    ids = []
    usedids = open('temp/ids.txt').readlines()
    with Pool(len(urls)) as p:
        idlistlist = p.map(getIdList, urls)
    for idlist in idlistlist:
        ids = ids + idlist
    for i in range(len(ids)):
        ids[i]= (ids[i],searchstring, usedids)

    #multithread fetching
    if len(ids) == 0: threadcount = 1
    elif len(ids) < 32: threadcount = len(ids) 
    else: threadcount = 32 

    with Pool(threadcount) as p:
        matchset = p.map(findPhraseTime, ids)


    errors = {} #we can throw errors later. some threads may have actually done some work
    matches = []
    for match in matchset:
        if isinstance(match, ExceptionWrapper):
            try:
                match.re_raise()
            except Exception as e:
                if not str(type(e)) in errors: errors[str(type(e))] = []
                errors[str(type(e))].append(e)
        else:
            matches = matches + match
    return matches, errors

def cleanInput(url:str)->list:
    urls = []
    #cleans channel
    m = re.search(r"/(@|channel/|c/|user/)(\S*)/*$", url)
    if m:
        urls.append(f"https://www.youtube.com/{m.group(1)}{m.group(2)}/shorts")
        urls.append(f"https://www.youtube.com/{m.group(1)}{m.group(2)}/videos")
        urls.append(f"https://www.youtube.com/{m.group(1)}{m.group(2)}/streams")

    if urls == []:return [url]
    else: return urls

if __name__== "__main__":
    #argparse when?
    searchstring = sys.argv[1]

    urls = []
    if ".txt" in sys.argv[2]: #can take a text file full of them. if youre into that.
        for line in open(sys.argv[2]).readlines():
            urls.append([searchstring,line.strip().strip("\n")])
    else:
        for arg in sys.argv[2:]:
            urls.append(arg)

    matches, errors = findList(searchstring, urls)
    matches = toUrls(matches, endtime=True)

    fn = f"matches_{''.join(ch for ch in searchstring if ch.isalnum())}_{datetime.now().timestamp()}.txt"
    with open(fn,"w") as f: #output file      
        for match in matches:
            f.write(match+"\n")   

    print("=====================================")
    print(f"{len(matches)} matches to \"{searchstring}\" found!")
    print(f"Written to file: {fn}")
    print("=====================================")
    print(errors.keys())
    for error in errors:
        for item in errors[error]:
            print("=====================================")
            print(item)