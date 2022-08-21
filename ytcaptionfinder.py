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
    with yt_dlp.YoutubeDL(ydl_opts) as yt:
        result = yt.extract_info( url,False)
    if 'entries' in result:
        results = []
        for item in result['entries']:
            results.append(item['id'])
        return results
    else:
        return [result['id']]



#takes a id and a string and downloads all the captions and returns a list of youtube links with the 
def getMatchUrls(args):
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
                                lines.append([charcount,int(event["tStartMs"]/1000)]) #builds a list of charactercount, timestamp pairs for all the segments
                                charcount = charcount + len(thisline)
                                script = script + thisline
                
                #finds all the matches and when in the video it happens
                for m in re.finditer(searchstring,script):
                    print(m)
                    lineplace = 0
                    while(m.start()>lines[lineplace][0]):
                        lineplace = lineplace + 1
                        if len(lines) == lineplace:
                            break
                    if len(lines) > lineplace:
                        if lineplace == 0:
                            matches.append(f"https://youtu.be/{id}?t={lines[lineplace][1]}")
                        else:
                            matches.append(f"https://youtu.be/{id}?t={lines[lineplace-1][1]}")
        return matches
    except Exception as e:
        return ExceptionWrapper(e)


def findList(searchstring:str, urls:list):
    #make folders
    if not os.path.exists(f"temp/"): os.makedirs(f"temp/")
    if not os.path.exists(f"temp/ids.txt"): open(f"temp/ids.txt", 'w'). close()
    
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
    if len(ids) < 32: threadcount = len(ids) 
    else: threadcount = 32 

    with Pool(threadcount) as p:
        matchset = p.map(getMatchUrls, ids)


    errors = {} #we can throw errors later. some threads may have actually done some work
    matches = []
    for match in matchset:
        if isinstance(matches, ExceptionWrapper):
            try:
                matches.re_raise()
            except Exception as e:
                if not str(type(e)) in errors: errors[str(type(e))] = []
                errors[str(type(e))].append(e)
        else:
            matches = matches + match
    return matches, errors


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