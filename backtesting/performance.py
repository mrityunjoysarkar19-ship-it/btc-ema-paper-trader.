def summarize(result):
    t,e=result["trades"],result["equity"]
    if t.empty:return {"total_trades":0,"win_rate":0,"profit_factor":0,"net_return":result["ending_equity"]-1,"max_drawdown":0}
    w=t.loc[t["return"]>0,"return"];l=t.loc[t["return"]<0,"return"]
    dd=e/e.cummax()-1
    return {"total_trades":len(t),"win_rate":float((t["return"]>0).mean()),
            "profit_factor":float(w.sum()/abs(l.sum())) if len(l) else float("inf"),
            "net_return":result["ending_equity"]-1,"max_drawdown":float(dd.min())}
