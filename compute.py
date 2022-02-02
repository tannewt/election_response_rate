import requests_cache
from bs4 import BeautifulSoup, NavigableString
import re
import csv
import pathlib

requests = requests_cache.CachedSession("result_cache")

site = "https://kingcounty.gov"

url = site + "/depts/elections/elections/past-elections.aspx"
requesters = requests.get(url)
requesters = BeautifulSoup(requesters.text, "lxml")
all_contests = []
for panel in requesters.find_all("div", class_="panel"):
    if panel.h4 is None:
        continue
    year = panel.h4.a.text.strip()
    print(year)
    for section in panel.find_all("section"):
        election_name = section.h5
        if election_name is None:
            # Bug with May 2016 presidential primary
            election_name = section.h2
        election_name = election_name.text.strip()
        print(election_name)
        results_link = section.find("a", string="Results")
        if results_link is None:
            break
        results_url = site + results_link["href"]
        results_page = requests.get(results_url)
        results_page = BeautifulSoup(results_page.text, "lxml")
        csv_link = results_page.find("a", href=re.compile(".*webresults.csv"))
        if csv_link is None:
            break
        csv_page = requests.get(csv_link["href"])
        last_contest = None
        contest_votes = 0
        for row in csv.DictReader(csv_page.text.split("\n")):
            contest = row["GEMS Contest ID"]
            if last_contest is None or contest != last_contest["GEMS Contest ID"]:
                if last_contest is not None:
                    all_contests.append(last_contest)
                last_contest = row
                last_contest["Total Votes"] = int(row["Votes"])
                for c in ("Candidate Sort Seq", "Ballot Response", "Party Preference", "Votes", "Percent of Votes"):
                    del last_contest[c]
                last_contest["Election Year"] = year
                last_contest["Election"] = election_name
            else:
                last_contest["Total Votes"] += int(row["Votes"])
        all_contests.append(last_contest)

out = pathlib.Path("contests.csv")
with out.open("w") as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=last_contest.keys())
    writer.writeheader()
    writer.writerows(all_contests)
