#!/usr/bin/python

"""
	strife - A phpbb3 TO THE LIST/FORUM two way converter
		(Might one day include Facebook)
	Setup:
	 1. Subscribe a mail address (eg: forum@ucc.asn.au) to all mailing lists
	 2. Subscribe to all topics in the forum
	 3. Edit variables appropriately, include list/forums to watch in variable `mail2forum`
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
username = open(".username","r").read().strip(" \r\n")
password = open(".password","r").read().strip(" \r\n")
browser = twill.get_browser()


forumurl = "https://forum.ucc.asn.au"
timeout = 10 # Magical timeout to wait for the automatic redirects to work
bouncemail = "matches@ucc.asn.au" # Will change to wheel@ if wheel don't murder me for this

# Email lists and the forum that they go to
mail2forum = {"ucc@ucc.asn.au" : "General", "tech@ucc.asn.au" : "Tech"}

# Numerical ID for the forums
forum2id = {"General" : "2", "Tech" : "4"}

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
	text += re.sub(r"Unsubsribe here: .*\n", "", email.get_payload()) + "\n\n"
	text += "-----\n"
	srcemail = "".join([e for e in msg["from"].split() if '@' in e])[1:-1]
	name = srcemail.split("@")[0]
	text += "View the lists at: http://lists.ucc.asn.au/\n"

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
		div = soup.findAll("div", {"class" : re.compile(r"^post bg[1|2].*$")})[-1]
		p = re.search(r"p(\d+)", div["id"]).groups()[0]
	else:
		# Find div for post
		div = soup.find("div", {"id" : "p"+p})

	# Get title of post
	title = div.find("a", {"href" : "#p"+p}).text.strip()
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
			i.replaceWith("#Image: "+i["src"] + "#")
		# Change links
		links = content.findAll("a")
		for l in links:
			l.replaceWith("#Link: "+l["href"]+"#")

		# Any other html tags will get lost here
		# Use '#' as a hacky way to put newlines in (they are also lost)
		content = content.text.strip().replace("#", "\n")

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
	#EmailDebug("Got an email...")
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
		# Work out list to associate the post with
		forum = forumName.groups()[0]
		email = None
		for k in mail2forum: # Check each key
			if mail2forum[k] == forum:
				email = k
				break
		# Couldn't find a list
		if email == None:
			sys.exit(0)

		# View the post; it is the first URL
		urls = re.findall(r"(https://.*)\n", msg.get_payload())
		assert(len(urls) > 0)
		post = GetPost(urls[0]) # Get post
		if (post["author"] == username):
			sys.exit(0) # Take no action if I authored the post
		if (post["content"] == ""):
			sys.exit(0)
		EmailDebug("Got forum notification; post "+urls[0]+" to list")
		EmailPost(post, email)
		ForumLogout()
		sys.exit(0)

	# If message is not a form -> lists post,
	if re.search(r"^On the forum, (.*) said:", msg.get_payload()) == None:

		# Look at "to" and "cc" emails and pick those that are being posted to the forum
		targets = msg["to"].split(",")
		if "cc" in msg:
			targets += msg["cc"].split(",")
		valid_targets = []
		for t in targets:
			for k in mail2forum:
				# Horrible regex that in theory gets only email addresses regardless of where they are, and no other crap
				if k not in valid_targets and re.search(r"(^|[\W<\"\'])"+k+"($|[\W>\"\'])", t, re.IGNORECASE) != None:
					valid_targets += [k]
	

		EmailDebug("Email from list to forum " + msg["from"] + " to " + msg["to"] + " valid_targets: " + str(valid_targets) + "\n\nSubject: " + msg["subject"] + "\nPayload:\n\n " + msg.get_payload())

		# For each target, post to the forum
		for t in valid_targets:
			p = PostEmail(msg, forum2id[mail2forum[t]])

		# Logout so that we will receive notifications again
		ForumLogout()
		sys.exit(0)
	
	# Bounce everything else
	EmailDebug("Not cross posting email from " + msg["from"] + " to " + msg["to"] + "\n\nSubject: " + msg["subject"] + "\nPayload:\n\n " + msg.get_payload())
	sys.exit(0)


