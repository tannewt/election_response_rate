import pandas
import matplotlib.pyplot as plt

df = pandas.read_csv("contests.csv")

df["Response Rate"] = df["Total Votes"] / df["Registered Voters for District"]

fig, axs = plt.subplots(figsize=(8, 8))
p = df.plot.box(column="Response Rate",
                by="Election",
                ax=axs,
                xlabel="Response Rate",
                ylabel="Election",
                vert=False,
                xlim=(0, 1))
plt.tight_layout()
fig.savefig("election_response_rate.png")

