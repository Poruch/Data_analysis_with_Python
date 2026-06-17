data = [150,200,100,140,170,180,50,-10]



border = [140,200]

valid = [x for x in data if border[0] <= x <= border[1] ]
avg = sum(valid) / len(valid)

new_data = [x if border[0] <= x <= border[1] else  avg for x in  data]

print(valid)
print(avg)
print(new_data)