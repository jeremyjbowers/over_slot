# OVER SLOT
This is the repository for a future website for Over Slot.

## Models
* Player — A player who appears in any number of rankings via the PlayerRanking model.
* Ranking — A ranking for a specific year on a specific date with a specific length. 
* PlayerRanking — A player's representation in a ranking. Denormalizes position, school and country.
* PlayerRankingCarryingTool — A generic assignment of carrying tools and scores that can be assigned to a PlayerRanking.
* Article — Written content that can reference players or rankings but is conceptually apart.

## Views / Templates / URLs
* Index — Homepage for the site.
* Articles — A paginated list of articles.
* Article detail — A single article identified by slug, which is headline (slugified) + a UUID4
* Rankings — A paginated list of rankings.
* Ranking detail — A single ranking identified by slug, with a list of PlayerRanking objects in order of PlayerRanking.rank.
* Player detail — A player's page, showing all rankings and articles a player appears in.
