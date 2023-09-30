# brightwheel-crawler

This is based on @remotephone's brightwheel crawling code.
**His original comments:**
"My kid will leave a school that uses the brightwheel app and I wanted to make sure I got all the pictures before he left. This uses selenium to crawl the page, loads all images, and then passes the auth info to requests and downloads all the image files. 

"I want to add image recognition to this to be able to parse out my kids face or remove ones that are likely just updates from the school, maybe that will come later."

**My comments:**
I have addded a few more features to this code and made a couple modifications.
- Changed the code to use a Chrome browser run with --remote-debugging-port=9014 (as per @orennir's suggestion)
- Commented out the login code since Brightwheel seems to sometimes ask "Are you a Bot?" which requires human intervention. (I mean... "No. But yes? A dad bot? Someone who would've paid $20 for you to just drop me my photos and videos in bulk with timestamps and comments in the metadata... but why have another revenue source? Let's go with Bottish.)
- Added logic to handle multiple students. Be aware: Brightwheel tends to log me out of their site after bulk grabs of media. Hence I grab all the URLs and metadata for all students before doing bulk grabs.
- Added logic to grab photos AND videos! W00t! Only... the code is a bit copy-and-paste, so I'm not proud of the lack of elegance their. Please avert your eyes; thankfully you should have a folder of your kid's pics -n- vids to distract you from that crusty copypython.
- Changed the entire logic for finding photos (or videos). Before, the code navigated through the web page elements and then, in a jarring left turn, just grabbed all the .jpg files using a regex on the whole page source. Why look through the elements if you were going to do that? Beats me. So I junked the regex and kept with the traversal. That lets me grab the date and time along with any text comments on each picture or video. That also lets me grab whatever media type is there, not just .jpg but also .jpeg, .png, etc.
- Hard-coded my daycare's GPS coordinates since the daycare doesn't geotag their photos. So maybe change that to your daycare.
- As mentioned above: now also grab the date and time and comments on the photo/video.
- Stick the metadata on the photos and videos via tags. This was great for photos but for videos... MP4s don't seem to have standard tags for create timestamp and GPS so... I didn't tag those. I stuck the timestamp in the title tag and the comment in comment and description.

Other important notes:
- The video download code uses some bits from @hankchen1728's py_m3u8_downloader and @songs18's m3u8_To_MP4.
- However, I had to alter the logic a bit to handle the Brightwheel URLs. (Basically, throw away everything after the first "?" to get the navigable part of the URL, then use that to get the stem for the streaming links in the m3u8 file.)

**HELP! I'm REALLY not used to running Python scripts!**
If you are not used to coding, running python scripts, and the like... there is a little guidance that may help.
- If you are on a windows machine, go here: https://realpython.com/installing-python/
- If you are on a Mac, go here: https://www.jcchouinard.com/install-python-on-macos/
- Open up a command prompt by running Powershell (Windows) or Terminal (MacOS) and then typing the following commands (and then pressing enter):
    python --version
    python3 --version
  - If python gives a version that is 3.<some numbers>, you are good and can run python 3 by just typing "python" at the command line
  - If python gives a version that is 2.<something>, then do not run that version since you need python 3.
  - If python3 gives a 3.<something> version number (like "Python 3.11.5"), then you are good and can run python 3 by just typing "python3" at the command line.
  - If neither of those worked, you need to install python 3. Follow instructions above.
- You will need to install some modules for this to work. For this you should use pip3. Instructions for installing and updating pip3 (which you should do before using it) are here: https://www.activestate.com/resources/quick-reads/how-to-install-and-use-pip3/
- Then, you will need to use pip3 to install some modules to make the brightscraper code work. To do this, you run pip3 at the command line, like so:
    pip3 install some_module_name
  - The modules you will need to install with pip3 are: yaml, tqdm, requests, selenium, piexif, Pillow, mutagen, and multiprocessing
- Once those are installed (they ran, you did not see them complain that they were unable to install), you can get ready to run the scraper script at the command line.
- First, change to the directory where you want to store your pictures and videos. Inside this directory, the script will create a "pics" and "vids" subdirectory for each student.
- Next, download the brightscraper.py and config.yml files to that directory.
- Download and run the Chrome browser with it set to listen to port 9014.
  - At another command line (run another Powershell or open another tab in Terminal), you can type
      chrome --remote-debugging-port=9014
  - or, on MacOS type
      /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9014
  - You should see the browser come up. Log in to brightwheel.
- Finally, using whichever python command runs python 3 (so "python" or "python3"), run the script like so:
    python3 brightscraper.py
- You will see the script navigate pages in the Chrome browser. DO NOT interfere with the Chrome browser since that can throw the code off in some circumstances.
- Now... if the video page is very long, the Chrome browser tab may crash with an "Aw Snap!" error. This typically happens for lots of videos. While it sucks, we can handle it.
  - In this case, you need to restrict how many pageloads you do.
  - Use Notepad++ or TextEditor to edit brightscraper.py; DO NOT USE WORD OR ANY OTHER WORD PROCESSOR! Word processors will change the characters "for appearances" but that messes up code.
  - Next, open up scraper.log and find the last time "Page load counter:" appears in the file. One less than that number is the most page loads you can do. (And, you might need to open a new browser tab and open Brightwheel there just to get a tab without any memory leaks -- so that you can depend on the page load counter.)
  - Go to line 160 -- or search for "kludge the loop" which is in a comment (the part of a line after #)
  - Change the code from
      while more2load is True:  # and counter < 110:
  - to
      while more2load is True and counter < 110:
  - So, essentially, delete three characters. Also, change that 110 to one less than the last page load count in the scraper.log file
  - Rerun the scraper script.
  - How to get the remaining photos?
    - Find the earliest video the script downlaoded.
    - I then used Firefox to load the whole list of all videos.
    - In Firefox, I downloaded (yes, by hand) the videos before what the script fetched.
    - Yes: this stinks. I know this is not elegant and it eats at my soul in a way that may only be painful to somebody who has been doing software engineering since high school and was brought up with lots of CS theory and good SWE practices as culture. I'm sorry -- and I mean that to you and to myself. I could try to fix the script to work with Firefox while not bugging out with possible "ARE YOU A BOT?!?" tests, but... it worked enough that the remaining videos were few and so script plus some manual downloads was the fastest solution.
    - So why keep this stinky solution? Spending more time with my family IS elegant. So I optimized for that. If you're here getting pics and vids of your kids, I suspect you too understand this tradeoff.

With all that, you should be good. If you are still having trouble, grab a tech friend, offer to pay them a favor back, and have them help you run the script.

Finally:
**If you are here from Brightwheel**
Folks, this took a lot of time even starting from the script @remotephone hacked together. I'm estimating I spent 20-25 hours on this with debugging and all that.

Honestly, if I could have paid $150 or $10/month of data to get all the photos and videos with tagging (timestamps, comments from the text in the photo/video event box, GPS -- even if just fixed at the daycare location)... I would have *happily* done that. Programmer and quant researcher time is not cheap but I spent that time to do this. Take that as what we economists would call "revealed preference" and an indication of demand.

That that all means is you are missing a golden opportunity. Yeah, I know: VCs love the subscription model, blah blah blah. But selling people their data to keep is both ethical and easy money. Buy yourself some more runway or some better numbers and SELL PEOPLE BULK DOWNLOADS OF THEIR PHOTOS AND VIDEOS OF THEIR KIDS. Any investment analyst would be happy to see you turning on this additional revenue source -- even if it's not an ongoing subscription. That or... wait for some parent to get annoyed and make a stink about pictures and videos of peoples' kids.
