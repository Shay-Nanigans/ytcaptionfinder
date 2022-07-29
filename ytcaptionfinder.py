from datetime import datetime
from gettext import find
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

#takes a tuple (searchstring, url, urlname) or a tuple (searchstring, url), downloads all the captions and returns a list of youtube links with the 
def getMatchUrls(strurlpair):
    try:
        if len(strurlpair) == 3:
            searchstring, url, urlname = strurlpair
        else:
            searchstring, url = strurlpair
            urlname = ''.join(ch for ch in url if ch.isalnum())

        #compiles the regex pattern to search
        searchstring = re.compile(rf"{searchstring}")

        ydl_opts = {
                    'outtmpl': f"{os.getcwd()}/temp/{urlname}/%(id)s.%(ext)s", 
                    'download_archive':os.join(f"{os.getcwd()}/temp/{urlname}/",'dl.txt'),
                    'format' : "mhtml", #i cant figure out how not to download something and this seems to be the smallest
                    'writesubtitles': True, 
                    'writeautomaticsub': True, 
                    'subtitlesformat':"json3",
                    'ignoreerrors':True

                }

        yt = yt_dlp.YoutubeDL(ydl_opts)
        yt.download(url)

        matches = []

        #searches everything it just downloaded for the string
        for file in os.listdir(f"temp/{urlname}/"): #right now it puts the threads into its own folder. theoretically it would be better to put them together but looking through a directory is easier
            if ".json3" not in file: continue
            print(file)
            with open(f"temp/{urlname}/{file}","r",encoding="utf8", errors='ignore') as f: #open the file
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
                                thisline = seg["utf8"].strip().replace("  ", " ") + " "
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
                            matches.append(f"https://youtu.be/{file.split('.')[0]}?t={lines[lineplace][1]}\n")
                        else:
                            matches.append(f"https://youtu.be/{file.split('.')[0]}?t={lines[lineplace-1][1]}\n")
        return matches
    except Exception as e:
        return ExceptionWrapper(e)


if __name__== "__main__":
    #argparse when?
    searchstring = sys.argv[1]

    urls = []
    if ".txt" in sys.argv[2]: #can take a text file full of them. if youre into that.
        for line in open(sys.argv[2]).readlines():
            urls.append([searchstring,line.strip().strip("\n")])
    else:
        for arg in sys.argv[2:]:
            urlname = None
            if "?list=" in arg:
                url = arg.split("?list=")[1]
            elif "?v=" in arg:
                url = arg.split("?v=")[1]
            elif "/c/" in arg:
                url = arg
                urlname = arg.split("/c/")[1]
            else:
                url = arg
            if urlname:
                urls.append([searchstring,url,urlname])
            else:
                urls.append([searchstring,url,url])

    #make folders
    if not os.path.exists(f"temp/"): os.makedirs(f"temp/")
    for url in urls:
        if not os.path.exists(f"temp/{url[2]}/"): os.makedirs(f"temp/{url[2]}/")

    #multithread fetching
    if len(urls) < 32: threadcount = len(urls) 
    else: threadcount = 32 

    with Pool(threadcount) as p:
        matchset = p.map(getMatchUrls, urls)


    errors = [] #we can throw errors later. some threads may have actually done some work
    with open(f"matches{datetime.now().timestamp()}.txt","w") as f: #output file
        for matches in matchset:
            if isinstance(matches, ExceptionWrapper):
                errors.append(matches)
            else:
                f.writelines(matches)
    for error in errors:
        error.re_raise()