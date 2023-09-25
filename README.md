# brightwheel-crawler

This is based on @remotephone's brightwheel crawling code. His original comments:
"My kid will leave a school that uses the brightwheel app and I wanted to make sure I got all the pictures before he left. This uses selenium to crawl the page, loads all images, and then passes the auth info to requests and downloads all the image files. 

"I want to add image recognition to this to be able to parse out my kids face or remove ones that are likely just updates from the school, maybe that will come later."

My comments:
I have addded a few more features to this code and made a couple modifications.
- Changed the code to use a Chrome browser run with --remote_debugging_port=9014 (as per @orennir's suggestion)
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
