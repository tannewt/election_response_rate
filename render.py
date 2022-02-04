import pandas
import matplotlib.pyplot as plt

df = pandas.read_csv("contests.csv")

df["Response Rate"] = df["Total Votes"] / df["Registered Voters for District"]

by = ["Election Year"]

fig, axs = plt.subplots(figsize=(8, 8))
general_only = df[df["Election Type"] == "general election"]
p = general_only.plot.box(column="Response Rate",
                by=list(reversed(by)),
                ax=axs,
                xlabel="General Election Response Rate",
                ylabel="Year",
                vert=False,
                xlim=(0, 1))
plt.tight_layout()
fig.savefig("election_response_rate.png")

# Full stats still
by = ["Election Year", "Election Month", "Election Type"]
stats = df.groupby(by=by).agg({"Response Rate": ("min", "max", "mean")})

stats.columns = [' '.join(col).strip() for col in stats.columns.values]

stats.to_csv("election_stats.csv")
