import requests_cache
from bs4 import BeautifulSoup, NavigableString
import re
import csv
import pathlib
import io
import zipfile

requests = requests_cache.CachedSession("result_cache")

site = "https://kingcounty.gov"

FIELDNAMES = {
    "April 2013 special election":
        "Precinct,Race,LEG,CC,CG,CounterGroup,Party,CounterType,SumOfCount".split(","),
    "February 2008 presidential primary and special election":
        "Race,Precinct,Leg District,County Council District,CounterGroup,Candidate,Count".split(","),
    "September 2006 primary election":
        "Race,Precinct,LEG,CC,CounterGroup,CounterType,SumOfCount".split(","),
    "November 2005 general election":
        "Race,Precinct,LEG,CC,CounterType,CounterGroup,SumOfCount".split(","),
    "February 2005 special election":
        "Race,Precinct,LEG,CC,CounterGroup,CounterType,SumOfCount".split(","),
    "September 2004 primary election":
        "Precinct,LEG,CC,Race,Party1,Party2,CounterType,Party3,CounterGroup,SumOfCount".split(","),
    "May 2004 special election":
        "Precinct,Race,??,LEG,CC,CounterType,CounterGroup,SumOfCount".split(","),
    "March 2004 special election":
        "Race,??,LEG,CC,Precinct,???,CounterType,CounterGroup,SumOfCount".split(","),
}

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
        month, _, election_type = election_name.split(" ", maxsplit=2)
        election_type = election_type.lower()
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
                    re.compile(".*cumulative-ecanvass.ashx\\?la=en"),
                    re.compile(".*ecanvass.ashx\\?la=en"))
        csv_link = None
        for pattern in patterns:
            csv_link = results_page.find("a", href=pattern)
            if csv_link is not None:
                break

        if csv_link is None:
            if election_name == "April 2011 special election":
                url = "https://kingcounty.gov/~/media/depts/elections/results/2011/201104-ecanvass.ashx?la=en"
            else:
                print("  no csv link")
                print(results_page)
                continue
        else:
            url = csv_link["href"].strip()
        if url[0] == "/":
            url = site + url
        csv_page = requests.get(url)
        f = io.BytesIO(csv_page.content)
        if zipfile.is_zipfile(f):
            z = zipfile.ZipFile(f)
            oz = f
            if not z.namelist():
                print("  bad zip")
                continue
            if len(z.namelist()) == 1:
                fn = z.namelist()[0]
            elif len(z.namelist()) == 2:
                fn = "CumulativeCanvassNov08.txt"
            elif len(z.namelist()) == 3:
                fn = "CumulativeCanvass1.txt"
                # The 2007 general had two more races in a second file. They are
                # for RTA and RTID whatever that is. (They're ignored.)
            else:
                print(z.namelist())
                print("  multiple files")
                continue
            if fn.endswith("xls"):
                print("  Excel file:", fn)
                continue
            fb = z.open(fn)
            f = io.TextIOWrapper(fb)
        else:
            f = io.StringIO(csv_page.text)
        f.seek(0)

        sample = f.read(1024)
        f.seek(0)
        sniffer = csv.Sniffer()
        try:
            dialect = sniffer.sniff(sample)
        except csv.Error as e:
            dialect = csv.excel
        try:
            has_header = sniffer.has_header(sample)
        except csv.Error as e:
            has_header = True
        fieldnames = None
        if not has_header:
            if election_name in FIELDNAMES:
                fieldnames = FIELDNAMES[election_name]
            else:
                print("  no header")
                print(f.readline())
                continue
        f.seek(0)
        reader = csv.DictReader(f, fieldnames, dialect=dialect)
        try:
            reader.fieldnames
        except csv.Error as e:
            print("  malformed csv")
            print(e)
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
                    last_contest["Election Month"] = month
                    last_contest["Election Type"] = election_type
                else:
                    last_contest["Total Votes"] += int(row["Votes"])
            all_contests.append(last_contest)
        elif (("Race" in reader.fieldnames or
              "RaceInfo" in reader.fieldnames or
              "RACE" in reader.fieldnames) and
             ("SumOfCount" in reader.fieldnames or
              "Count" in reader.fieldnames or
              "COUNT" in reader.fieldnames) and
             ("CounterType" in reader.fieldnames or
              "Candidate" in reader.fieldnames or
              "CountType" in reader.fieldnames or
              "COUNTERTYPE" in reader.fieldnames or
              "CountHeading" in reader.fieldnames)):

            for k in ("SumOfCount", "Count", "COUNT"):
                if k in reader.fieldnames:
                    count_key = k
                    break
            for k in ("Race", "RaceInfo", "RACE"):
                if k in reader.fieldnames:
                    race_key = k
                    break
            for k in ("CounterType", "Candidate", "CountType", "COUNTERTYPE", "CountHeading"):
                if k in reader.fieldnames:
                    counter_key = k
                    break
            contests_by_name = {}
            for row in reader:
                if (row.get("CounterGroup", "Total") != "Total" or
                    row.get("COUNTERGROUP", "Total") != "Total"):
                    continue
                contest = row[race_key]
                if contest not in contests_by_name:
                    contest_data = {}
                    contest_data["Total Votes"] = 0
                    contest_data["Registered Voters for District"] = 0
                    contest_data["Election Year"] = year
                    contest_data["Election Month"] = month
                    contest_data["Election Type"] = election_type
                    contest_data["GEMS Contest ID"] = row[race_key]
                    contests_by_name[contest] = contest_data
                    all_contests.append(contest_data)
                else:
                    contest_data = contests_by_name[contest]

                # Data is split by precinct so we'll be adding a bunch
                if "." in row[count_key]:
                    count = int(float(row[count_key]))
                else:
                    count = int(row[count_key])
                if row[counter_key] == "Registered Voters":
                    contest_data["Registered Voters for District"] += count
                elif row[counter_key] == "Times Counted":
                    contest_data["Total Votes"] += count
        else:
            print("unknown csv")
            print(reader.fieldnames)
    print()

out = pathlib.Path("contests.csv")
with out.open("w") as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=last_contest.keys())
    writer.writeheader()
    writer.writerows(all_contests)
