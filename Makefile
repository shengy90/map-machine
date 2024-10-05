# .PHONY: example1
# example1:
#     poetry run python map_machine/main.py tile --boundary-box 0.03720769296088362,51.50181629766614,0.06648977541743915,51.50948681057793 --zoom 16


.PHONY: getcityairport
getcityairport:
	poetry run python map_machine/main.py tile --boundary-box 0.03720769296088362,51.50181629766614,0.06648977541743915,51.50948681057793 --zoom 16