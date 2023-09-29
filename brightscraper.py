import logging
import os
import re
import glob
import time
import yaml
import tqdm
import shutil
from datetime import date, datetime, timedelta
from functools import partial

import requests
from requests.models import Response
from selenium.common.exceptions import ElementNotVisibleException, NoSuchElementException
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
import subprocess

import piexif
import piexif.helper
from PIL import Image, ExifTags
#from PIL.ExifTags import GPS, TAGS
import mutagen
from mutagen.mp4 import MP4
from pathlib import Path
import random

from multiprocessing.dummy import Pool
#import m3u8_To_MP4


"""
From the original brightscraper comments:
I was saving pictures ad hoc through the brightwheel app, but got way behind
and didn't want to lose them if my kid changed schools or lost access to the app.
This uses selenium to crawl a BrightWheel (https://mybrightwheel.com/) profile
for images, find all of them, pass the cookies to requests, and then download
all images in bulk. Works with current site design as off 6/24/19

Dale's updated scraper comments:
Oy, this needed some work. The Brightwheel site ignores the date ranges, so I
scrapped that. I also had to fix some of the selenium calls to use the preferred
(more general) find_element() method. This code also did not handle multiple kids,
so I added that. The code also used to go through all this work to select certain
parts of the web source only to then do a global search for images. That's not
very... elegant, so I keep the context and search for images forward from where I
was last looking. That incremental approach also lets me grab the last-seen date
and, for each picture, the time plus any comments. I then pop the datetime and
comments into EXIF tags -- along with GPS coordinates for my childcare location.
I'm also trying to get it to download videos, but we'll see if that pans out.
"""

def config_parser():
    """parse config file in config.yml if present"""
    try:
        with open("config.yml", 'r') as config:
            cfg = yaml.safe_load(config)
        username = cfg['bwuser']
        password = cfg['bwpass']
        signin_url = cfg['bwsignin']
        kidlist_url = cfg['bwlist']
        startdate = cfg['startdate']
        enddate = cfg['enddate']
        media_folder = cfg['mediadir']
    except FileNotFoundError:
        logging.error('[!] No config file found, check config file!')
        raise SystemExit

    return username, password, signin_url, kidlist_url, startdate, enddate, media_folder


# Get the first URL and populate the fields
def signme_in(browser, username, password, signin_url):
    """Populate and send login info using U/P from config"""

    browser.get(signin_url)
    loginuser = browser.find_element(By.ID, 'username')
    loginpass = browser.find_element(By.ID, 'password')
    loginuser.send_keys(username)
    loginpass.send_keys(password)

    # Submit login, have to wait for page to change
    try:
        loginpass.submit()
        WebDriverWait(browser, 5).until(EC.url_changes(signin_url))
    except:
        logging.error('[!] - Unable to authenticate - Check credentials')
        raise SystemExit

    return browser


def get_students(browser, kidlist_url):
    """ Gets the list of kids so we can iterate through them. This also makes
    things more modular so we can also get videos and notes"""
    browser.get(kidlist_url)
    time.sleep(2+2*random.random())

    # This xpath is generic enough to find any student listed.
    # You need to iterate through a list you create if you have more than one
    try:
        students = browser.find_elements(By.XPATH,
            "//a[contains(@href, '/students/')]"
            )
    except:
        logging.error('[!] - Unable to find profiles page, check target')
        raise SystemExit
    return students

def load_full_page(media_type, browser, student_page, startdate, enddate):
    """
    Navigate to a student's page, go to their feed, load the page for just
    photos/videos/whatever media type, scroll to the bottom to load them all.
    The startdate and enddate do not currently work with Brightwheel's site.
    """

    try:
        browser.get(student_page)
    except:
        logging.error('[!] - Unable to get profile page, check target')
        raise SystemExit
    time.sleep(1+random.random())

    # Get to feed, this is where the pictures are
    feed = browser.find_element(By.LINK_TEXT, 'Feed')
    feed.click()
    time.sleep(1+random.random())

    # OG comment: Populate the selector for date range to load all images
    # Except Brightwheel's page does not currently work with date ranges,
    # just with media types... so, I commented out the date logic in
    # case it ever starts working again.
    #start_date = browser.find_element(By.NAME, 'start_date')  # 'activity-start-date')
    #start_date.send_keys(startdate)
    #end_date = browser.find_element(By.NAME, 'end_date')  # 'activity-end-date')
    #end_date.send_keys(enddate)
    select = browser.find_element(By.ID, 'select-input-2')
    select.send_keys(media_type)
    select.send_keys(Keys.ENTER)

    # This gets us to the media feed
    media_feed = browser.find_element(By.CLASS_NAME, 'StudentFeed')
    # Then it's easy to get the Apply button and click it
    media_feed.find_element(By.XPATH, './form/button').click()

    try:
        last_height = browser.execute_script("return document.body.scrollHeight")
        counter = 0
        more2load = True
        # Yes, the commented code below is utter trash. In my defense: I had to
        # kludge the loop by not letting the counter get too high since
        # Brightwheel's page overwhelms Chrome for the videos if it gets too big
        # (which seems to occur around the 2-year mark if a video or two are
        # uploaded each day on average.
        # Commented out below (along with the print statement to figure out
        # how high you can go) but here in case you too need it.
        while more2load is True:   # and counter < 3:
            #print("[?] Page load counter: {}".format(counter))
            # Look for the "Load More" button...
            try:
                counter += 1
                button = WebDriverWait(browser, 7).until(
                    EC.presence_of_element_located((
                        By.XPATH, '//button[text()="Load more"]')))
                button.click()
            except:
                if counter == 1:
                    logging.info('[!] No Loading button found!')
                else:
                    logging.debug('[?] Loading button no longer found')
            browser.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);")

            # Wait to load the page.
            time.sleep(3+2*random.random())

            # Calculate new scroll height and compare with last scroll height.
            new_height = browser.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                logging.info('[-] Page fully loaded...')
                more2load = False
            # and save the new height for comparison in the next trip through the loop
            last_height = new_height
    except ElementNotVisibleException:
        logging.debug('[?] Web page interactions did not fully work')
    return media_feed


def pic_finder(browser, photo_feed, student_name):
    """
    This is the core logic of the script... but I changed it a bit from the original.
    Yes, navigate through the site, but then traverse all the elements to find all the
    photos and create an iterable list of image URLs and metadata.
    """

    photo_matches = []
    exif_date_format = "%Y:%m:%d"
    processing_date = date.today().strftime(exif_date_format)
    processing_time = "00:00:00"
    # Now walk through the web page grabbing all the cards for media we want
    # Keep track of the date (assumed in reverse chronological order) and also
    # grab any text comments on the videos. I also stick the GPS coordinates
    # for my daycare on each record -- since the daycare does not put GPS on
    # the photos they take. However, I end up not using this since MP4 GPS
    # tags are, apparently, not standard. Oh well.
    # This greatly differs from the past logic which navigated the page and
    # then, oddly, just did a regex on the whole page source losing all context
    # that could be gotten in traversing the elements. So, I junked that and
    # save the metadata I find.
    elements = photo_feed.find_elements(By.XPATH, './div')
    for elem in elements:
        try:
            day_label = elem.find_element(By.CSS_SELECTOR, "div[class^='activity-card-module-dayLabel']")
            new_date = day_label.text.split('\n')[0]
            if new_date == "Yesterday":
                processing_date = (date.today() - timedelta(days=1)).strftime(exif_date_format)
            elif new_date != "Today":
                processing_date = datetime.strptime(new_date, "%m/%d/%Y").strftime(exif_date_format)
        except NoSuchElementException:
            logging.debug('[?] Continuing with current date')
        
        try:
            card_element = elem.find_element(By.CSS_SELECTOR, "div[class^='card activity-card-module-card']")
        except NoSuchElementException:
            continue
        time_text = card_element.find_element(By.CSS_SELECTOR, "span[class^='activity-card-module-date']").text
        processing_time = datetime.strptime(time_text, "%I:%M %p").strftime("%H:%M:00")
        content_element = card_element.find_element(By.CSS_SELECTOR, "div[class^='activity-card-module-content']")
        comment = None
        try:
            comment_element = content_element.find_element(By.CSS_SELECTOR, "p[class^='activity-card-module-text']")
            comment = comment_element.text if comment_element.text != "" else None
        except NoSuchElementException:
            logging.debug('[?] No comment on photo')
        try:
            photo_url = content_element.find_element(By.CSS_SELECTOR,'a').get_attribute('href')
        except NoSuchElementException:
            logging.error('[!] No photo URL found!')
            continue

        photo_match = {
            "DateTime": processing_date+" "+processing_time,
            "PhotoURL": photo_url,
            "GPSLatitude": ((41, 1), (52, 1), (98, 10)),
            "GPSLatitudeRef": "N",
            "GPSLongitude": ((87, 1), (37, 1), (3432, 100)),
            "GPSLongitudeRef": "W",
            "GPSAltitude": (181, 1),
            "GPSAltitudeRef": 0
            }
        if comment:
            photo_match["UserComment"] = comment
            logging.info('[-] Found comment {} for photo timestamp {}'.format(comment, photo_match['DateTime']))
        photo_matches.append(photo_match)

    count_matches = len(photo_matches)
    if count_matches == 0:
        logging.error('[!] No Images found to download! Check the source target page')
    else:
        logging.info('[!] Found {} files to download for {}...'
                         .format(count_matches, student_name))

    return browser, photo_matches


def vid_finder(browser, video_feed, student_name):
    """
    This is the core logic of the script... but I changed it a bit from the original.
    Yes, navigate through the site, but then traverse all the elements to find all the
    photos and create an iterable list of video URIs (m3u8 links) and metadata.
    """

    video_matches = []
    exif_date_format = "%Y:%m:%d"
    processing_date = date.today().strftime(exif_date_format)
    processing_time = "00:00:00"
    # Now walk through the web page grabbing all the cards for media we want
    # Keep track of the date (assumed in reverse chronological order) and also
    # grab any text comments on the videos. I also stick the GPS coordinates
    # for my daycare on each record -- since the daycare does not put GPS on
    # the photos they take. However, I end up not using this since MP4 GPS
    # tags are, apparently, not standard. Oh well.
    # This greatly differs from the past logic which navigated the page and
    # then, oddly, just did a regex on the whole page source losing all context
    # that could be gotten in traversing the elements. So, I junked that and
    # save the metadata I find.
    elements = video_feed.find_elements(By.XPATH, './div')
    for elem in elements:
        try:
            day_label = elem.find_element(By.CSS_SELECTOR, "div[class^='activity-card-module-dayLabel']")
            new_date = day_label.text.split('\n')[0]
            if new_date == "Yesterday":
                processing_date = (date.today() - timedelta(days=1)).strftime(exif_date_format)
            elif new_date != "Today":
                processing_date = datetime.strptime(new_date, "%m/%d/%Y").strftime(exif_date_format)
        except NoSuchElementException:
            logging.debug('[?] Continuing with current date')
        
        try:
            card_element = elem.find_element(By.CSS_SELECTOR, "div[class^='card activity-card-module-card']")
        except NoSuchElementException:
            continue
        time_text = card_element.find_element(By.CSS_SELECTOR, "span[class^='activity-card-module-date']").text
        processing_time = datetime.strptime(time_text, "%I:%M %p").strftime("%H:%M:00")
        content_element = card_element.find_element(By.CSS_SELECTOR, "div[class^='activity-card-module-content']")
        comment = None
        try:
            comment_element = content_element.find_element(By.CSS_SELECTOR, "p[class^='activity-card-module-text']")
            comment = comment_element.text if comment_element.text != "" else None
        except NoSuchElementException:
            logging.debug('[?] No comment on video')
        try:
            video_url = content_element.find_element(By.CSS_SELECTOR,"source[type^='application/x-mpegURL']").get_attribute('src')
        except NoSuchElementException:
            logging.error('[!] No video URL found!')
            continue

        video_match = {
            "DateTime": processing_date+" "+processing_time,
            "VideoURL": video_url,
            "GPSLatitude": ((41, 1), (52, 1), (98, 10)),
            "GPSLatitudeRef": "N",
            "GPSLongitude": ((87, 1), (37, 1), (3432, 100)),
            "GPSLongitudeRef": "W",
            "GPSAltitude": (181, 1),
            "GPSAltitudeRef": 0
            }
        if comment:
            video_match["UserComment"] = comment
            logging.info('[-] Found comment {} for video timestamp {}'.format(comment, video_match['DateTime']))
        video_matches.append(video_match)

    count_matches = len(video_matches)
    if count_matches == 0:
        logging.error('[!] No Videos found to download! Check the source target page')
    else:
        logging.info('[!] Found {} files to download for {}...'
                         .format(count_matches, student_name))

    return browser, video_matches


def get_photos(media_folder, browser, student_name, matches):
    """
    Since Selenium doesn't handle saving images/videos well, requests can
    do this for us, but we need to pass it the cookies. Also, we may see
    multiple photos in the same minute, so we need to make sure there are
    no collisions in filenames (since we use the timestamp as the name).
    """
    # First, check if there is no work to do
    if len(matches) == 0:
        logging.info("[-] No photos to grab for {}".format(student_name))
        return

    cookies = browser.get_cookies()
    session = requests.Session()
    for cookie in cookies:
        session.cookies.set(cookie['name'], cookie['value'])

    photo_names_register = {}
    photo_dir = os.path.join(media_folder, "pics-"+student_name)
    # creating pics directory if it does not already exist
    Path(photo_dir).mkdir(parents=True, exist_ok=True)
    for match in matches:
        photo_filename_base = match["DateTime"].replace(":","-")
        file_name, file_extension = match["PhotoURL"].split("/")[-1].split('?')[0].split('.')
        photo_filename = photo_filename_base+"."+file_extension
        # resolve name clashes
        if photo_filename in photo_names_register:
            photo_clash_counter = photo_names_register[photo_filename]
            photo_names_register[photo_filename] += 1
            photo_filename = photo_filename_base+"-{}.{}".format(photo_clash_counter, file_extension)
        else:
            photo_names_register[photo_filename] = 1
        full_photo_filename = os.path.join(photo_dir, photo_filename)
        logging.info('[-] - Downloading {} to {}'.format(file_name+"."+file_extension, photo_filename))
        try:
            request = session.get(match["PhotoURL"])
            open(full_photo_filename, 'wb').write(request.content)
        except:
            logging.error('[!] - Failed to save {}'.format(match["PhotoURL"]))
            continue
        time.sleep(1+random.random())
        try:
            img = Image.open(full_photo_filename)
            exif_dict = piexif.load(img.info['exif'])
            exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = match["DateTime"]
            exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = match["DateTime"]
            exif_dict['GPS'][piexif.GPSIFD.GPSLatitude] = match["GPSLatitude"]
            exif_dict['GPS'][piexif.GPSIFD.GPSLatitudeRef] = match["GPSLatitudeRef"]
            exif_dict['GPS'][piexif.GPSIFD.GPSLongitude] = match["GPSLongitude"]
            exif_dict['GPS'][piexif.GPSIFD.GPSLongitudeRef] = match["GPSLongitudeRef"]
            exif_dict['GPS'][piexif.GPSIFD.GPSAltitude] = match["GPSAltitude"]
            exif_dict['GPS'][piexif.GPSIFD.GPSAltitudeRef] = match["GPSAltitudeRef"]
            if "UserComment" in match:
                exif_dict["Exif"][piexif.ExifIFD.UserComment] = piexif.helper.UserComment.dump(
                    match["UserComment"], encoding="unicode")
            exif_bytes = piexif.dump(exif_dict)
            img.save(full_photo_filename, "jpeg", exif=exif_bytes, quality=100) # was exif_bytes
        except:
            logging.error('[!] - Could not write EXIF data for file {}'.format(photo_filename))
    logging.info("[-] Finished writing all photo files for {}".format(student_name))



class Video_Decoder(object):
    def __init__(self, x_key: dict, m3u8_http_base: str = ""):
        self.method = x_key["METHOD"] if "METHOD" in x_key.keys() else ""
        self.uri = decode_key_uri(m3u8_http_base+x_key["URI"]) \
            if "URI" in x_key.keys() else ""
        self.iv = x_key["IV"].lstrip("0x") if "IV" in x_key.keys() else ""

        # print("URI", self.uri)
        # print("IV", self.iv)

    def decode_aes_128(self, video_fname: str):
        subprocess.run([
            "openssl",
            "aes-128-cbc",
            "-d",
            "-in", video_fname,
            "-out", "out" + video_fname,
            "-nosalt",
            "-iv", self.iv,
            "-K", self.uri
        ])
        subprocess.run(["rm", "-f", video_fname])
        subprocess.run(["mv", "out" + video_fname, video_fname])

    def __call__(self, video_fname: str):
        if self.method == "AES-128":
            self.decode_aes_128(video_fname)
        else:
            pass


# video helper routines
def decode_key_uri(URI: str):
    uri_req = requests.get(URI) #, headers=header)
    uri_str = "".join(["{:02x}".format(c) for c in uri_req.content])
    return uri_str

def decode_ext_x_key(key_str: str):
    # TODO: check if there is case with "'"
    key_str = key_str.replace('"', '').lstrip("#EXT-X-KEY:")
    v_list = re.findall(r"[^,=]+", key_str)
    key_map = {v_list[i]: v_list[i+1] for i in range(0, len(v_list), 2)}
    return key_map

def download_ts_file(ts_url: str, session, store_dir: str, attempts: int = 10):
    # TODO: check 403 Forbidden
    ts_fname = ts_url.split('/')[-1].split('?')[0]
    ts_dir = os.path.join(store_dir, ts_fname)
    ts_res = None

    for tryct in range(attempts):
        try:
            ts_res = session.get(ts_url, headers={}) # session was requests
            if ts_res.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(.5)

    if isinstance(ts_res, Response) and ts_res.status_code == 200:
        with open(ts_dir, 'wb+') as f:
            f.write(ts_res.content)
    else:
        print(f"Failed to download streaming file: {ts_fname}.")


def download_m3u8_videostream(browser, session, match, outdir, mp4_outfile):
    m3u8_link = match["VideoURL"]
    startTime = datetime.now()

    # Reading the m3u8 file
    m3u8_http_base = ""

    if m3u8_link.startswith("http"):
        m3u8_content = session.get(m3u8_link).content.decode("utf-8") # session: was requests
        m3u8_http_base = '/'.join(m3u8_link.split('?')[0].split("/")[0:-1])
    else:
        m3u8_content = ""
        # read m3u8 file content
        with open(m3u8_link, 'r') as f:
            m3u8_content = f.read()
            if not m3u8_content:
                logging.error("The m3u8 file: {m3u8_link} is empty.")
                return

    # Parsing the content in m3u8
    m3u8 = m3u8_content.split('\n')
    ts_url_list = []
    ts_names = []
    x_key_dict = dict()
    for i_str in range(len(m3u8)):
        line_str = m3u8[i_str]
        if line_str.startswith("#EXT-X-KEY:"):
            x_key_dict = decode_ext_x_key(line_str)
        elif line_str.startswith("#EXTINF"):
            ts_url = m3u8[i_str+1]
            ts_names.append(ts_url.split('/')[-1].split('?')[0])
            if not ts_url.startswith("http"):
                ts_url = m3u8_http_base+"/"+ts_url
            ts_url_list.append(ts_url)
    logging.info("[-] There are {} files to download for link {}...".format(len(ts_url_list), m3u8_link))
    video_decoder = Video_Decoder(x_key=x_key_dict, m3u8_http_base=m3u8_http_base)

    # Setting temporary paths
    ts_folder = os.path.join(outdir, ".tmp_ts")
    os.makedirs(ts_folder, exist_ok=True)
    os.chdir(ts_folder)

    # Using multithreading to parallel downloading
    pool = Pool(20)
    gen = pool.imap(partial(download_ts_file, session=session, store_dir='.'), ts_url_list)
    # create a progress bar for the downloading
    for _ in tqdm.tqdm(gen, total=len(ts_url_list)):
        pass
    pool.close()
    pool.join()
    time.sleep(1)
    logging.info("[-] Streaming files downloading completed.")

    # Start to merge all *.ts files
    downloaded_ts = glob.glob("*.ts")
    # Decoding videos
    for ts_fname in tqdm.tqdm(downloaded_ts, desc="Decoding the *.ts files"):
        video_decoder(ts_fname)

    # not sure why this says it is ordered; not sure that's guaranteed from glob.glob
    ordered_ts_names = [ts_name for ts_name in ts_names if ts_name in downloaded_ts]

    if len(ordered_ts_names) > 200:
        mp4_fnames = []
        part_num = len(ordered_ts_names) // 200 + 1
        for _i in range(part_num):
            sub_files_str = "concat:"

            _idx_list = range(200)
            if _i == part_num - 1:
                _idx_list = range(len(ordered_ts_names[_i * 200:]))
            for ts_idx in _idx_list:
                sub_files_str += ordered_ts_names[ts_idx + _i * 200] + '|'
            sub_files_str = sub_files_str.rstrip('|')

            # files_str += 'part_{}.mp4'.format(_i) + '|'
            mp4_fnames.append('part_{}.mp4'.format(_i))
            subprocess.run([
                'ffmpeg', '-i', sub_files_str, '-c', 'copy', '-bsf:a', 'aac_adtstoasc', 'part_{}.mp4'.format(_i)
            ])

        with open("mylist.txt", 'w') as f:
            for mp4_fname in mp4_fnames:
                f.write(f"file {mp4_fname}\n")
        subprocess.run([
            'ffmpeg', "-f",
            "concat", "-i", "mylist.txt",
            '-codec', 'copy', mp4_outfile
        ])
    else:
        files_str = "concat:"
        for ts_filename in ordered_ts_names:
            files_str += ts_filename+'|'
        files_str = files_str.rstrip('|')
        ffmpeg_command_bits = ["ffmpeg", "-i", files_str, "-c", "copy", "-bsf:a", "aac_adtstoasc", mp4_outfile]
        subprocess.run(ffmpeg_command_bits)

    # tag MP4 file
    try:
        vidfile = MP4(mp4_outfile)
        vidfile["\xa9nam"] = match["DateTime"]
        if 'UserComment' in match:
            vidfile["desc"] = match["UserComment"]
            vidfile["\xa9cmt"] = match["UserComment"]
        logging.info("[-] Tagged video {}".format(vidfile.pprint()))
        vidfile.save()
        mp4_newpath = os.path.join(outdir, os.path.basename(mp4_outfile))
        mp4_fullpath = os.path.abspath(mp4_outfile)
        os.chdir(outdir)
        shutil.move(mp4_fullpath, mp4_newpath)
        endTime = datetime.now()
        logging.info("[-] Pieced together video {}, time spent: {}".format(mp4_outfile, endTime - startTime))
    except:
        logging.error("[!] Failed to open and write file {}".format(mp4_outfile))

    # Remove all split *.ts
    shutil.rmtree(ts_folder)


def get_videos(media_folder, browser, student_name, matches):
    """
    Since Selenium doesn't handle saving images/videos well, requests
    can do this for us, but we need to pass it the cookies. Also, we may see
    multiple videos in the same minute, so we need to make sure there are
    no collisions in filenames (since we use the timestamp as the name).
    """
    # First, check if there is no work to do
    if len(matches) == 0:
        logging.info("[-] No videos to grab for {}".format(student_name))
        return

    cookies = browser.get_cookies()
    session = requests.Session()
    for cookie in cookies:
        session.cookies.set(cookie['name'], cookie['value'])

    video_names_register = {}
    video_dir = os.path.join(media_folder, "vids-"+student_name)
    # creating vids directory if it does not already exist
    Path(video_dir).mkdir(parents=True, exist_ok=True)
    os.chdir(video_dir)
    for match in matches:
        video_filename_base = (match["DateTime"].replace(":","-"))+".mp4"
        file_name, file_extension = match["VideoURL"].split("/")[-1].split('?')[0].split('.')
        video_filename = video_filename_base+"."+file_extension
        # resolve name clashes
        if video_filename in video_names_register:
            video_clash_counter = video_names_register[video_filename]
            video_names_register[video_filename] += 1
            video_filename = video_filename_base+"-{}.{}".format(video_clash_counter, file_extension)
        else:
            video_names_register[video_filename] = 1
        logging.info('[-] - Downloading {} stream files to {}'.format(file_name+"."+file_extension, video_filename))
        download_m3u8_videostream(browser, session, match, video_dir, video_filename)
    logging.info("[-] Finished writing all video files for student {}".format(student_name))



def clear_cookies(browser):
    """ Clear out the cookies we have been using"""
    session = requests.Session()    
    try:
        session.cookies.clear()
        browser.delete_all_cookies()
        logging.info('[-] - Cleared cookies')
    except:
        logging.error('[!] - Failed to clear cookies')


def main():
    """Init logging and set up Chrome connection"""
    logging.basicConfig(filename='scraper.log', filemode='w', level=logging.DEBUG)

    options = webdriver.ChromeOptions() # Options()
    options.debugger_address = '127.0.0.1:9014'
    browser = webdriver.Chrome(options=options)
    #browser = webdriver.Firefox()

    username, password, signin_url, kidlist_url, startdate, enddate, media_folder = config_parser()

    # commented out since the code requires having a manually logged-in Chrome browser
    #browser = signme_in(browser, username, password, signin_url)
    students = get_students(browser, kidlist_url)
    # we get the students in an ephemeral iterable; save it to something permanent
    student_list = []
    for student in students:
        student_list.append({"name": student.get_property('text'),
                             "page": student.get_property('href')})
    
    photo_matches = {}
    video_matches = {}
    # it is important to not join these loops
    # we get the links from the webpages first because the bulk
    # grab of media (after first loop) often ends with Brightwheel
    # logging us out -- so try to defer that to the end
    for student in student_list:
        feed = load_full_page("Photo", browser, student['page'], startdate, enddate)
        browser, pic_matches = pic_finder(browser, feed, student['name'])
        photo_matches[student['name']] = pic_matches
        feed = load_full_page("Video", browser, student['page'], startdate, enddate)
        browser, vid_matches = vid_finder(browser, feed, student['name'])
        video_matches[student['name']] = vid_matches
    for student_name in photo_matches.keys():
        pic_matches = photo_matches[student_name]
        get_photos(media_folder, browser, student_name, pic_matches)
    for student_name in video_matches.keys():
        vid_matches = video_matches[student_name]
        get_videos(media_folder, browser, student_name, vid_matches)
    clear_cookies(browser)
    logging.shutdown()

if __name__ == "__main__":
    main()
