#!/usr/bin/python

"""
	strife - A phpbb3 TO THE LIST/FORUM two way converter
		(Might one day include Facebook)
	Setup:
	 1. Subscribe a mail address (eg: forum@ucc.asn.au) to all mailing lists
	 2. Subscribe to all topics in the forum
	 3. Edit variables appropriately, include list/forums to watch in variable `mail2forum` and formums in `forum2mail`
	 4. Edit /etc/aliases to pass email to this script
	 5. Profit (or get murdered)

"""

import sys
import os
import re
import twill
import time
import email
from email.mime.text import MIMEText
import smtplib
import BeautifulSoup
import base64

# Keep the credentials in files that won't be under git
if __name__ == "__main__" and sys.argv != None and len(sys.argv) >= 1:
	username = open(os.path.dirname(sys.argv[0])+"/.username","r").read().strip(" \r\n")
	password = open(os.path.dirname(sys.argv[0])+"/.password","r").read().strip(" \r\n")
browser = twill.get_browser()


forumurl = "https://forum.ucc.asn.au"
timeout = 20 # Magical timeout to wait for the automatic redirects to work
bouncemail = "matches@ucc.asn.au" # Will change to wheel@ if wheel don't murder me for this

# Email lists and the forum that they go to
mail2forum = {
	"ucc" : "General",
	"tech" : "Tech",
	"ucc-announce" : "News/Announcements",
	"strife" : "Strife",
	"hwc" : "Tech",
	"committee" : "Committee"
}

# Forums and the lists that they go to
forum2mail = {
	"General" : "ucc",
	"Tech" : "tech",
	"News/Announcements" : "ucc", #Autoposting to ucc-announce is bad.
	"Strife" : "strife",
	"Committee" : "committee"
}

# Numerical ID for the forums
forum2id = {
	"General" : "2", 
	"Tech" : "4", 
	"News / Announcements" : "5", 
	"Strife" : "8"
}

def ForumLogin(force = False):
	""" Login to the forum
	    Will visit login page directly if force == True
	    Otherwise, will only login if currently on the login page
	"""
	if force:
		twill.commands.go(forumurl+"/ucp.php?mode=login")
		time.sleep(timeout)

	soup = BeautifulSoup.BeautifulSoup(GetHTML())
	if soup.find("form", {"id": "login"}) != None:
		twill.commands.fv("login", "username", username)
		twill.commands.fv("login", "password", password)
		twill.commands.browser.submit("login")
		time.sleep(timeout)

def ForumLogout():
	""" Logout from the forum (necessary to keep receiving notifications) """
	twill.commands.go(forumurl+"/ucp.php?mode=logout")
	time.sleep(timeout)

def GetForumTopics(forum):
	""" Get a list of topics under the forum """
	twill.commands.go(forumurl+"/viewforum.php?f="+str(forum))
	old = sys.stdout
	sys.stdout = open("/dev/null", "w")
	links = twill.commands.showlinks()
	sys.stdout.close() 
	sys.stdout = old
	topics = []
	for l in links:
		if l.url.split("?")[0] == "./viewtopic.php":
			topics += [l]
	return topics


def PostEmail(email, forum):
	""" Post an email to the forum """
	url = forumurl + "/posting.php"
	params = None
	# Strip out [LIST] parts of subject
	subject = re.sub(r"\[.*\] ", "",email["subject"])
	# Was it a reply? Try and find the relevant topic to reply into
	if subject.split(" ")[0] in ["Re:", "Re", "RE:", "RE", "re:", "re"]:
		for topic in GetForumTopics(forum):
			if re.search(" ".join(subject.split(" ")[1:]), topic.text, re.IGNORECASE) != None:
				t = re.search(r"t=(\d+)", topic.url).groups()[0]
				params = "?mode=reply&f="+forum+"&t="+t
				break

	# Wasn't a reply (or couldn't find the topic) - make a new topic
	if params == None: 
		params = "?mode=post&f="+forum
	url += params

	twill.commands.go(url)
	ForumLogin()
	#EmailDebug(GetHTML())
	twill.commands.fv("postform", "subject", subject)

	# Content to post
	text = "On the lists, " + email["from"] + " wrote:\n\n"
	for line in email.get_payload().split("\n"):
		if re.match(r"Unsubscribe here: (.*)",line) == None:
			text += line + "\n"

	# Not needed
	#text += "-----\n"
	#srcemail = "".join([e for e in msg["from"].split() if '@' in e])[1:-1]
	#name = srcemail.split("@")[0]
	#text += "View the lists at: http://lists.ucc.asn.au/\n"

	twill.commands.fv("postform", "message", text)
	twill.commands.browser.submit("post")
	time.sleep(timeout)

	# Find the post and return its url
	# TODO: Fix (? Probably not needed)
	"""
	soup = BeautifulSoup.BeautifulSoup(GetHTML())
	bg1 = soup.findAll("div", {"class" : "post bg1 online"})[-1]
	bg2 = soup.findAll("div", {"class" : "post bg2 online"})[-1]
	p1 = int(bg1.find("h3").find("a")["href"].strip("\"#p"))
	p2 = int(bg2.find("h3").find("a")["href"].strip("\"#p"))
	p = max(p1, p2)
	return forumurl+"/viewtopic.php?f="+forum+"&t="+t+"#p"+str(p)
	"""



def GetHTML():
	""" Get the HTML of the currently visited page """
	# Horrible hacks are afoot (twill prints lots of stuff to stdout automatically)
	old = sys.stdout
	sys.stdout = open("/dev/null", "w")
	t = twill.commands.show()
	sys.stdout.close
	sys.stdout = old
	# Twill has a nicer API than other things, but I wish it wouldn't print to stdout unless you asked it to.
	return t

def GetPost(url, plainText=True):
	""" Parse the url to find the identified post, or the newest post if none is identified """
	# Get post id
	p = re.search(r"p=(\d+)", url)
	if p == None:
		p = re.search(r"#p(\d+)", url)
	if p != None:
		p = p.groups()[0]

	# Visit post
	twill.commands.go(url)
	ForumLogin()
	html = GetHTML()
	soup = BeautifulSoup.BeautifulSoup(html)

	# If no post was specified, search for the newest post
	if p == None:
		index = -1
		div = soup.findAll("div", {"class" : re.compile(r"^post bg[1|2].*$")})
		if len(div) == 0:
			div = soup.findAll("div", {"class" : "post"})
		if len(div) == 0:
			div = soup.findAll("dt", {"title" : re.compile(r".* posts")})
			if len(div) != 0:
				a = div[0].find("a", {"class" : "topictitle"})
				if a != None:
					return GetPost(a["href"],plainText)
				else:
					div = []

		if len(div) == 0:
			raise Exception("Can't find post!? URL is "+url)

		div = div[index]
		p = re.search(r"p(\d+)", div["id"]).groups()[0]
	else:
		# Find div for post
		div = soup.find("div", {"id" : "p"+p})

	# Get title of post
	title = div.find("a", {"href" : "#p"+p}).text.strip()
	# Replace quotation marks
	title = title.replace("&quot;", "\"")
	

	# Get author of post
	author = div.find("p", {"class" : "author"})
	author = author.find("strong").text.strip()
	# Get content of post
	content = div.find("div", {"class" : "content"})

	if not plainText:
		content = str(content) # TODO: Make email cope with this (?)
	else:
		
		

		# Change blockquotes
		quotes = content.findAll("blockquote")
		for q in quotes:
			q.replaceWith("##Quote: " + q.text.strip()+"##")

		# Change images
		imgs = content.findAll("img")
		for i in imgs:
			i.replaceWith(i["src"])
		# Change links
		links = content.findAll("a")
		for l in links:
			l.replaceWith(l["href"])
		# <br>
		brrs = content.findAll("br")
		for b in brrs:
			b.replaceWith("#")		

		# Any other html tags will get lost here
		# Use '#' as a hacky way to put newlines in (they are also lost)
		content = content.text.strip().replace("#", "\n").replace("&quot;","\"");

	# Return dict representing the post
	return {"url" : url, "title" : title, "author" : author, "content" : content}

def EmailPost(post, tothelist):
	""" Post a forum post TO THE LISTS """
	# Construct message
	postMsg = "On the forum, " + post["author"] + " said:\n\n"
	postMsg += post["content"] + "\n\n"
	postMsg += "-----\n"
	postMsg += "Note: HTML content in the forum post may have been lost.\n"
	postMsg += "View the forum post here: " + post["url"] + "\n\n"
	postMsg += tothelist
	
	# TO THE LISTS
	s = smtplib.SMTP("localhost")
	m = MIMEText(postMsg)
	m["Subject"] = post["title"]
	m["From"] = tothelist 
	m["To"] = tothelist
	s.sendmail(m["From"], [m["To"]], m.as_string())
	s.quit()

def PlainEmail(email, text):
	""" Quick plaintext email to the specified address """
	s = smtplib.SMTP("localhost")
	m = MIMEText(text)
	m["Subject"] = "forum@ucc.asn.au"
	m["From"] = email
	m["To"] = email
	s.sendmail(m["From"], [m["To"]], m.as_string())
	s.quit()

def EmailDebug(text):
	""" Debugging emails (debugging things via emails is certainly an experience I do not recommend) """
	PlainEmail("matches@ucc.asn.au", text)

"""
	Doing the pythonic thing don't do the things unless we are __main__
"""
if __name__ == "__main__":
	EmailDebug("I got an email!")
	# Parse email from stdin (to be piped via /etc/aliases in postfix)
	full_message = sys.stdin.readlines()
	msg = email.message_from_string("".join(full_message))
	#to, from, subject, body are keys
	assert("to" in msg)
	assert("from" in msg)
	assert("subject" in msg)



	# Is the message a forum notification?
	# NOTE Parsing subject doesn't work since phpbb does some kind of shitty encoding on it that python doesn't understand
	forumName = re.search(r"You are receiving this notification because you are watching the forum,\n\"(.*)\" at \"forum.ucc.asn.au\"", msg.get_payload(), re.IGNORECASE)
	if forumName != None: #Yes, yes it is
		EmailDebug("Getting a notification from the forum...")
		# Work out list to associate the post with
		forum = forumName.groups()[0]
		emails = []
		for k in forum2mail: # Check each key
			if k == forum and k not in emails:
				emails += [forum2mail[k]+"@ucc.asn.au"]

		# Couldn't find a list
		if len(emails) == 0:
			EmailDebug("No list associated with forum " + forum)
			sys.exit(0)


		# View the post; it is the first URL
		urls = re.findall(r"(https://.*)\n", msg.get_payload())
		assert(len(urls) > 0)
		post = GetPost(urls[0]) # Get post
		EmailDebug("Got forum notification; post "+urls[0]+" from forum \""+forum+"\" to lists " + str(emails))
		if (post["author"] == username or post["content"] == ""):
			EmailDebug("Post is empty or my own; abort.")
			sys.exit(0)

		for e in emails:
			try:
				EmailPost(post, e)
				EmailDebug("Posted to "+e+" successfully!")
			except Exception,ex:
				EmailDebug("EmailPost to "+e+" failed: " + str(ex))
		ForumLogout()
		EmailDebug("Logged out successfully.");
		sys.exit(0)

	# If message is not a form -> lists post,
	if re.search(r"^On the forum, (.*) said:", msg.get_payload()) == None:

		EmailDebug("Got email to list; finding targets")
		# Look at "to" and "cc" emails and pick those that are being posted to the forum
		targets = msg["to"].split(",")
		if "cc" in msg:
			targets += msg["cc"].split(",")
		valid_targets = []
		for t in targets:
			for k in mail2forum:
				# Horrible regex that in theory gets only email addresses regardless of where they are, and no other crap
				if k not in valid_targets and re.search(r"(^|[\W<\"\'])"+k+"@ucc.*($|[\W>\"\'])", t, re.IGNORECASE) != None:
					valid_targets += [k]
	

		EmailDebug("Email from list to forum " + msg["from"] + " to " + msg["to"] + " valid_targets: " + str(valid_targets) + " -> " + str(map(lambda e : mail2forum[e], valid_targets)) + "\n\nSubject: " + msg["subject"] + "\nPayload:\n\n " + msg.get_payload())

		# For each target, post to the forum
		for t in valid_targets:
			try:
				p = PostEmail(msg, forum2id[mail2forum[t]])
				EmailDebug("Successfully posted to target " + str(t))
			except Exception,ex:
				EmailDebug("Post email to "+mail2forum[t]+" failed: " + str(ex) + "\nHTML was " + GetHTML())

		# Logout so that we will receive notifications again
		ForumLogout()
		EmailDebug("Successfully logged out.");
	
	EmailDebug("Exiting.")
	sys.exit(0)


