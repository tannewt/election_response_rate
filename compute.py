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
last_contest = None
for panel in requesters.find_all("div", class_="panel"):
    if panel.h4 is None:
        continue
    year = panel.h4.a.text.strip()
    print(year)
    sections = panel.find_all("section")
    if not sections:
        sections = panel.find_all("ul")[1:]
    for section in sections:
        election_name = section.h5
        if election_name is None:
            # Bug with May 2016 presidential primary
            election_name = section.h2
        if election_name is None:
            election_name = section.find_previous_sibling("h5")

        election_name = election_name.text.strip()
        print(election_name)
        results_link = section.find("a", string="Results")
        if results_link is None:
            # If no results link, then check the section itself
            results_page = section
        else:
            results_url = site + results_link["href"]
            results_page = requests.get(results_url)
            results_page = BeautifulSoup(results_page.text, "lxml")

        patterns = (re.compile(".*webresults.csv"),
                    re.compile(".*/newresults.csv"),
                    re.compile(".*/results.csv"),
                    re.compile(".*rows.csv\\?accessType=DOWNLOAD.*"),
                    re.compile(".*ecanvass.ashx\\?la=en"))
        csv_link = None
        for pattern in patterns:
            csv_link = results_page.find("a", href=pattern)
            if csv_link is not None:
                break

        if csv_link is None:
            print("no csv link")
            print(results_page)
            continue
        url = csv_link["href"].strip()
        if url[0] == "/":
            url = site + url
        csv_page = requests.get(url)
        reader = csv.DictReader(csv_page.text.split("\n"))
        try:
            reader.fieldnames
        except csv.Error:
            print("malformed csv")
            continue
        # Check for modern layout
        if ("GEMS Contest ID" in reader.fieldnames or 
            "ContName" in reader.fieldnames):
            last_contest = None
            for row in reader:
                if "GEMS Contest ID" in row:
                    contest = row["GEMS Contest ID"]
                elif "ContName" in row:
                    contest = row["ContName"]
                if last_contest is None or contest != last_contest["GEMS Contest ID"]:
                    if last_contest is not None:
                        all_contests.append(last_contest)
                    first_votes = int(row["Votes"])
                    if "GEMS Contest ID" in row:
                        last_contest = {}
                        for k in ("GEMS Contest ID", "Registered Voters for District"):
                            last_contest[k] = row[k]
                    else:
                        registered = str(int(float(row["Registered"])))
                        last_contest = {
                            "GEMS Contest ID": row["ContName"],
                            "Registered Voters for District": registered
                        }
                    last_contest["Total Votes"] = first_votes
                    
                    last_contest["Election Year"] = year
                    last_contest["Election"] = election_name
                else:
                    last_contest["Total Votes"] += int(row["Votes"])
            all_contests.append(last_contest)
        elif "Race" in reader.fieldnames and "SumOfCount" in reader.fieldnames:
            contests_by_name = {}
            for row in reader:
                contest = row["Race"]
                if contest not in contests_by_name:
                    contest_data = {}
                    contest_data["Total Votes"] = 0
                    contest_data["Registered Voters for District"] = 0
                    contest_data["Election Year"] = year
                    contest_data["Election"] = election_name
                    contest_data["GEMS Contest ID"] = row["Race"]
                    contests_by_name[contest] = contest_data
                    all_contests.append(contest_data)
                else:
                    contest_data = contests_by_name[contest]

                # Data is split by precinct so we'll be adding a bunch
                if "." in row["SumOfCount"]:
                    count = int(float(row["SumOfCount"]))
                else:
                    count = int(row["SumOfCount"])
                if row["CounterType"] == "Registered Voters":
                    contest_data["Registered Voters for District"] += count
                elif row["CounterType"] == "Times Counted":
                    contest_data["Total Votes"] += count
        else:
            print("unknown csv")
            print(reader.fieldnames)

out = pathlib.Path("contests.csv")
with out.open("w") as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=last_contest.keys())
    writer.writeheader()
    writer.writerows(all_contests)
